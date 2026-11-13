"""Detection: ensemble of a pothole specialist + a crack model, OpenCV severity, ByteTrack video tracking, drawing.

Models (first existing file wins for each role):
  pothole : models/pothole_best.pt (fine-tuned here) -> models/potholenet_yolo11m.pt (PotholeNet, Indian roads)
  cracks  : models/best.pt -> models/rdd2022_yolov8m.pt (RDD2022 D00/D10/D20; its weak D40 head is ignored)
The crack model can be switched off for speed (RD_CRACKS=0 or live "potholes only" mode).
"""
import os
import threading
import time
from collections import Counter, defaultdict
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np

from . import config, scoring, severity as sevmod

_lock = threading.RLock()
_infer_lock = threading.Lock()
_models = None

# BGR, same palette as the web UI
COLORS = {
    "pothole": (48, 59, 255),
    "alligator_crack": (10, 159, 255),
    "transverse_crack": (255, 132, 10),
    "longitudinal_crack": (242, 90, 191),
    "manhole": (199, 140, 20),
    "speed_breaker": (5, 183, 242),
    "debris": (60, 120, 140),
    "barricade": (200, 200, 200),
}
SEV_THICK = {"Low": 1.0, "Medium": 1.5, "High": 2.2, "Minor": 1.0, "Moderate": 1.4, "Severe": 1.9, "Critical": 2.5}
PREFIX = {"pothole": "PH", "alligator_crack": "AC", "transverse_crack": "TC", "longitudinal_crack": "LC",
          "manhole": "MH", "speed_breaker": "SB", "debris": "DB", "barricade": "BR"}
CLS_ID = {c: i for i, c in enumerate(config.CLASSES)}

POTHOLE_WEIGHTS = [os.getenv("RD_POTHOLE_WEIGHTS", ""), str(config.ROOT / "models" / "pothole_best.pt"),
                   str(config.ROOT / "models" / "potholenet_yolo11m.pt")]
CRACK_WEIGHTS = [os.getenv("RD_WEIGHTS", ""), str(config.ROOT / "models" / "best.pt"),
                 str(config.ROOT / "models" / "rdd2022_yolov8m.pt")]
FEATURE_WEIGHTS = [os.getenv("RD_FEATURE_WEIGHTS", ""), str(config.ROOT / "models" / "features_best.pt")]
FEATURE_CONF = float(os.getenv("RD_FEATURE_CONF", "0.5"))
POTHOLE_CONF = float(os.getenv("RD_POTHOLE_CONF", "0.25"))
CRACK_CONF = float(os.getenv("RD_CRACK_CONF", "0.30"))
USE_CRACKS = os.getenv("RD_CRACKS", "1") != "0"


def _first(paths):
    for p in paths:
        if p and Path(p).exists():
            return p
    return None


def _load():
    global _models
    with _lock:
        if _models is None:
            from ultralytics import YOLO
            roles = []
            pw = _first(POTHOLE_WEIGHTS)
            if pw:
                m = YOLO(pw)
                cmap = {k: "pothole" for k, v in m.names.items() if config.canonical_class(v) == "pothole"}
                roles.append(SimpleNamespace(role="pothole", model=m, path=pw, cmap=cmap, conf=POTHOLE_CONF))
            cw = _first(CRACK_WEIGHTS)
            if cw:
                m = YOLO(cw)
                cmap = {k: config.canonical_class(v) for k, v in m.names.items()
                        if config.canonical_class(v) in CLS_ID and (not pw or config.canonical_class(v) != "pothole")}
                roles.append(SimpleNamespace(role="cracks", model=m, path=cw, cmap=cmap, conf=CRACK_CONF))
            fw = _first(FEATURE_WEIGHTS)
            if fw:
                m = YOLO(fw)
                cmap = {k: config.canonical_class(v) for k, v in m.names.items()
                        if config.canonical_class(v) in CLS_ID and config.canonical_class(v) not in
                        ("pothole", "longitudinal_crack", "transverse_crack", "alligator_crack")}
                roles.append(SimpleNamespace(role="features", model=m, path=fw, cmap=cmap, conf=FEATURE_CONF))
            if not roles:
                raise RuntimeError("No weights in models/. Run ml/download_data.py")
            _models = roles
    return _models


def get_model():  # backwards compat: primary model
    return _load()[0].model


def model_info():
    roles = _load()
    return {"weights": " + ".join(Path(r.path).name for r in roles),
            "models": [{"role": r.role, "weights": Path(r.path).name, "classes": sorted(set(r.cmap.values()))}
                       for r in roles],
            "classes": config.CLASSES}


def reload_model():
    global _models
    with _lock:
        _models = None
    return model_info()


def preprocess(img):
    """Low-light / low-contrast correction with CLAHE on the L channel (only when needed)."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    mean, std = float(gray.mean()), float(gray.std())
    if mean < 80 or std < 35:
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        l = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(l)
        return cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR), True
    return img, False


class Dets:
    """Minimal numpy detections container accepted by Ultralytics' BYTETracker."""

    def __init__(self, xyxy, conf, cls):
        self.xyxy = np.asarray(xyxy, np.float32).reshape(-1, 4)
        self.conf = np.asarray(conf, np.float32).reshape(-1)
        self.cls = np.asarray(cls, np.float32).reshape(-1)

    @property
    def xywh(self):
        x = self.xyxy
        return np.stack([(x[:, 0] + x[:, 2]) / 2, (x[:, 1] + x[:, 3]) / 2, x[:, 2] - x[:, 0], x[:, 3] - x[:, 1]], 1)

    def __len__(self):
        return len(self.conf)

    def __getitem__(self, k):
        return Dets(self.xyxy[k], self.conf[k], self.cls[k])


def _iou(a, b):
    x1, y1 = np.maximum(a[0], b[:, 0]), np.maximum(a[1], b[:, 1])
    x2, y2 = np.minimum(a[2], b[:, 2]), np.minimum(a[3], b[:, 3])
    inter = np.clip(x2 - x1, 0, None) * np.clip(y2 - y1, 0, None)
    return inter / ((a[2] - a[0]) * (a[3] - a[1]) + (b[:, 2] - b[:, 0]) * (b[:, 3] - b[:, 1]) - inter + 1e-9)


def infer(img, cracks=None, conf_floor=None):
    """Run the ensemble on one BGR frame. Returns Dets with unified class ids (config.CLASSES)."""
    roles = _load()
    cracks = USE_CRACKS if cracks is None else cracks
    boxes, confs, clss = [], [], []
    with _infer_lock:
        for r in roles:
            if r.role in ("cracks", "features") and not cracks:
                continue
            c = r.conf if conf_floor is None else min(r.conf, conf_floor)
            res = r.model.predict(img, conf=c, iou=config.IOU_THRESHOLD, imgsz=config.IMG_SIZE, quantize=16,
                                  verbose=False)[0]
            b = res.boxes
            if b is None or not len(b):
                continue
            for xy, cf, k in zip(b.xyxy.cpu().numpy(), b.conf.cpu().numpy(), b.cls.cpu().numpy().astype(int)):
                name = r.cmap.get(int(k))
                if name is None:
                    continue
                boxes.append(xy)
                confs.append(float(cf))
                clss.append(CLS_ID[name])
    d = Dets(boxes, confs, clss)
    if len(d):
        # a crack box that mostly overlaps a pothole box is the pothole's broken rim: drop it
        pot = d.xyxy[d.cls == CLS_ID["pothole"]]
        keep = np.ones(len(d), bool)
        if len(pot):
            for i in range(len(d)):
                if d.cls[i] != CLS_ID["pothole"] and _iou(d.xyxy[i], pot).max() > 0.5:
                    keep[i] = False
        d = d[keep]
    return d


def make_row(frame, cls, x1, y1, x2, y2, conf, track_id=None):
    h, w = frame.shape[:2]
    a = sevmod.analyze(frame, cls, x1, y1, x2, y2, conf)
    lane = scoring.lane_factor(((x1 + x2) / 2) / w)
    return {"class_name": cls, "confidence": round(float(conf), 4), "x1": float(x1), "y1": float(y1),
            "x2": float(x2), "y2": float(y2), "track_id": track_id, "lane": lane, **a}


def rows_from(frame, d: Dets):
    return [make_row(frame, config.CLASSES[int(k)], *xy, cf) for xy, cf, k in zip(d.xyxy, d.conf, d.cls)]


def draw(img, rows, label_fn=None):
    """Class-coloured damage outline + box with corner brackets (thicker = more severe) and an ID tag."""
    out = img.copy()
    overlay = out.copy()
    base = max(2, int(round(min(out.shape[:2]) / 360)))
    fs = max(0.5, min(out.shape[:2]) / 1100)
    for r in rows:
        col = COLORS.get(r["class_name"], (255, 255, 255))
        for poly in r.get("polygon") or []:
            if len(poly) >= 3:
                cv2.fillPoly(overlay, [np.array(poly, np.int32)], col)
    out = cv2.addWeighted(overlay, 0.35, out, 0.65, 0)
    for r in rows:
        col = COLORS.get(r["class_name"], (255, 255, 255))
        t = max(2, int(base * SEV_THICK.get(r.get("severity"), 1.0)))
        x1, y1, x2, y2 = int(r["x1"]), int(r["y1"]), int(r["x2"]), int(r["y2"])
        for poly in r.get("polygon") or []:
            if len(poly) >= 3:
                cv2.polylines(out, [np.array(poly, np.int32)], True, col, max(1, t - 1), cv2.LINE_AA)
        cv2.rectangle(out, (x1, y1), (x2, y2), col, 1, cv2.LINE_AA)
        c = max(8, int(min(x2 - x1, y2 - y1) * 0.25))
        ct = t + 2
        for (ax, ay, bx, by, cx, cy) in ((x1, y1 + c, x1, y1, x1 + c, y1), (x2 - c, y1, x2, y1, x2, y1 + c),
                                         (x1, y2 - c, x1, y2, x1 + c, y2), (x2 - c, y2, x2, y2, x2, y2 - c)):
            cv2.polylines(out, [np.array([[ax, ay], [bx, by], [cx, cy]], np.int32)], False, col, ct, cv2.LINE_AA)
        text = label_fn(r) if label_fn else (f'{PREFIX.get(r["class_name"], "RD")} {r["severity"]} '
                                             f'{r["confidence"]:.2f}')
        (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, fs, max(1, base - 1))
        ty = y1 - 6 if y1 - th - 12 > 0 else y2 + th + 10
        cv2.rectangle(out, (x1, ty - th - 7), (x1 + tw + 12, ty + 5), col, -1)
        cv2.putText(out, text, (x1 + 6, ty), cv2.FONT_HERSHEY_SIMPLEX, fs, (255, 255, 255), max(1, base - 1),
                    cv2.LINE_AA)
    return out


def crop(img, r, pad=0.15):
    h, w = img.shape[:2]
    bw, bh = r["x2"] - r["x1"], r["y2"] - r["y1"]
    x1 = int(max(0, r["x1"] - bw * pad)); y1 = int(max(0, r["y1"] - bh * pad))
    x2 = int(min(w, r["x2"] + bw * pad)); y2 = int(min(h, r["y2"] + bh * pad))
    c = img[y1:y2, x1:x2]
    return c if c.size else img


_extra = None


def _extra_pothole_models():
    """Second-opinion pothole models for the accurate (upload) mode."""
    global _extra
    with _lock:
        if _extra is None:
            from ultralytics import YOLO
            paths = [config.ROOT / "models" / "potholenet_yolo11m.pt"]
            primary = next((r.path for r in _load() if r.role == "pothole"), None)
            _extra = [YOLO(str(p)) for p in paths if p.exists() and str(p) != primary]
    return _extra


def infer_accurate(img):
    """Upload mode: pothole ensemble (fine-tuned + PotholeNet, each with a horizontal-flip pass) fused with
    Weighted Boxes Fusion, as used by the CRDDC2022 winners; cracks / features from the normal ensemble."""
    try:
        from ensemble_boxes import weighted_boxes_fusion
    except ImportError:
        return infer(img)
    base = infer(img)
    keep = base.cls != CLS_ID["pothole"]
    h, w = img.shape[:2]
    pmodels = [r.model for r in _load() if r.role == "pothole"] + _extra_pothole_models()
    B, S, L = [], [], []
    with _infer_lock:
        for m in pmodels:
            pot_ids = {k for k, v in m.names.items() if config.canonical_class(v) == "pothole"}
            for flipped in (False, True):
                v = img[:, ::-1].copy() if flipped else img
                r = m.predict(v, conf=0.05, iou=0.6, imgsz=config.IMG_SIZE, quantize=16, verbose=False)[0].boxes
                sel = [i for i, c in enumerate(r.cls.cpu().numpy().astype(int)) if c in pot_ids]
                xy = r.xyxy.cpu().numpy()[sel].copy()
                if flipped and len(xy):
                    xy[:, [0, 2]] = w - xy[:, [2, 0]]
                xy[:, [0, 2]] /= w
                xy[:, [1, 3]] /= h
                B.append(np.clip(xy, 0, 1).tolist())
                S.append(r.conf.cpu().numpy()[sel].tolist())
                L.append([0] * len(sel))
    fb, fs, _ = weighted_boxes_fusion(B, S, L, iou_thr=0.55, skip_box_thr=0.05, conf_type="avg")
    fb, fs = np.array(fb).reshape(-1, 4) * [w, h, w, h], np.array(fs)
    ok = fs >= POTHOLE_CONF
    pot = Dets(fb[ok], fs[ok], [CLS_ID["pothole"]] * int(ok.sum()))
    return Dets(np.vstack([base.xyxy[keep], pot.xyxy]), np.concatenate([base.conf[keep], pot.conf]),
                np.concatenate([base.cls[keep], pot.cls]))


ACCURATE_UPLOADS = os.getenv("RD_ACCURATE", "1") != "0"


def detect_image(img):
    proc, enhanced = preprocess(img)
    t0 = time.time()
    d = infer_accurate(proc) if ACCURATE_UPLOADS else infer(proc)
    rows = rows_from(img, d)
    return rows, {"enhanced": enhanced, "ms": int((time.time() - t0) * 1000)}


TRACK_ARGS = SimpleNamespace(tracker_type="bytetrack", track_high_thresh=0.22, track_low_thresh=0.08,
                             new_track_thresh=0.25, track_buffer=45, match_thresh=0.8, fuse_score=True)


class Tracker:
    """ByteTrack + per-track aggregation (majority class, best frame, crop). Used by video files and live mode."""

    def __init__(self):
        from ultralytics.trackers.byte_tracker import BYTETracker
        self.bt = BYTETracker(TRACK_ARGS)
        self.tracks = {}
        self.display = {}
        self.frame_idx = 0
        self.w = self.h = 0

    def disp(self, tid):
        if tid not in self.display:
            self.display[tid] = len(self.display) + 1
        return self.display[tid]

    def step(self, frame, cracks=None, time_s=None):
        """Detect + track one frame. Returns list of rows for the currently visible tracks."""
        self.h, self.w = frame.shape[:2]
        proc, _ = preprocess(frame)
        d = infer(proc, cracks=cracks, conf_floor=0.1)
        out = self.bt.update(d, proc) if len(d) else self.bt.update(Dets(np.zeros((0, 4)), [], []), proc)
        self.frame_idx += 1
        rows = []
        for x1, y1, x2, y2, tid, score, k, *_ in out:
            tid = int(tid)
            cls_now = config.CLASSES[int(k)]
            tr = self.tracks.setdefault(tid, {"hits": 0, "classes": Counter(), "best": None, "best_q": -1,
                                              "first": self.frame_idx, "crop": None})
            tr["hits"] += 1
            tr["classes"][cls_now] += float(score)
            tr["last"] = self.frame_idx
            cls = tr["classes"].most_common(1)[0][0]
            x1, y1 = max(0.0, float(x1)), max(0.0, float(y1))
            x2, y2 = min(float(self.w), float(x2)), min(float(self.h), float(y2))
            confirmed = tr["hits"] >= config.TRACK_MIN_HITS
            cache = tr.get("ana")
            if not confirmed and cache is None:
                # unconfirmed flicker: skip the OpenCV analysis, it is only drawn as a dashed box
                r = {"class_name": cls, "confidence": round(float(score), 4), "x1": x1, "y1": y1, "x2": x2, "y2": y2,
                     "track_id": tid, "lane": scoring.lane_factor(((x1 + x2) / 2) / self.w), "polygon": [],
                     "severity": "Minor", "severity_score": 0.0, "water": False, "size_index": 0.0, "depth_index": 0.0,
                     "roughness_index": 0.0, "area_ratio": 0.0, "perspective": 1.0, "damage_fill": 0.0}
            elif cache is not None and self.frame_idx - cache["at"] < 3 and cache["cls"] == cls:
                # reuse the analysis from up to 2 frames ago, shifting the outline with the tracked box
                dx, dy = x1 - cache["x1"], y1 - cache["y1"]
                r = dict(cache["row"], confidence=round(float(score), 4), x1=x1, y1=y1, x2=x2, y2=y2,
                         lane=scoring.lane_factor(((x1 + x2) / 2) / self.w),
                         polygon=[[[px + dx, py + dy] for px, py in poly] for poly in cache["row"]["polygon"]])
            else:
                r = make_row(frame, cls, x1, y1, x2, y2, score, tid)
                tr["ana"] = {"at": self.frame_idx, "cls": cls, "x1": x1, "y1": y1, "row": r}
            r["confirmed"] = confirmed
            r["display_id"] = self.disp(tid) if r["confirmed"] else None
            r["hits"] = tr["hits"]
            q = float(score) * (0.5 + r["severity_score"])
            if q > tr["best_q"]:
                tr["best_q"] = q
                tr["best"] = dict(r, frame_index=self.frame_idx, time_s=time_s)
                tr["crop"] = crop(frame, r)
            rows.append(r)
        return rows

    def unique(self):
        return [t for t in self.tracks.values() if t["hits"] >= config.TRACK_MIN_HITS]

    def by_class(self):
        return dict(Counter(t["classes"].most_common(1)[0][0] for t in self.unique()))

    def final_rows(self):
        rows = []
        for tid, tr in self.tracks.items():
            if tr["hits"] < config.TRACK_MIN_HITS or tr["best"] is None:
                continue
            b = dict(tr["best"])
            b["class_name"] = tr["classes"].most_common(1)[0][0]
            b.update(crop=tr["crop"], frames_seen=tr["hits"], track_id=self.display.get(tid, tid))
            rows.append(b)
        rows.sort(key=lambda r: r["track_id"])
        return rows


def label_track(r):
    tag = f'{PREFIX.get(r["class_name"], "RD")}#{r["display_id"]}' if r.get("display_id") else "..."
    return f'{tag} {r["severity"]} {r["confidence"]:.2f}'


def detect_video(path, out_path, frame_cb=None):
    """Track defects through a video. Returns (unique track rows, meta). Annotated H.264 video is written."""
    import imageio.v2 as iio

    cap = cv2.VideoCapture(str(path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    stride = max(1, config.VIDEO_FRAME_STRIDE)
    writer = iio.get_writer(str(out_path), fps=fps / stride, codec="libx264", quality=7, macro_block_size=8,
                            ffmpeg_log_level="error", pixelformat="yuv420p")
    tk = Tracker()
    idx = processed = 0
    t0 = time.time()
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if idx % stride:
                idx += 1
                continue
            if processed >= config.VIDEO_MAX_FRAMES:
                break
            rows = tk.step(frame, time_s=idx / fps)
            shown = [r for r in rows if r["confirmed"]]
            ann = draw(frame, shown, label_track)
            hud(ann, len(tk.unique()), tk.by_class())
            writer.append_data(cv2.cvtColor(ann, cv2.COLOR_BGR2RGB))
            processed += 1
            idx += 1
            if frame_cb and total:
                frame_cb(min(1.0, idx / total))
    finally:
        cap.release()
        writer.close()
    out = tk.final_rows()
    meta = {"fps": fps, "frames_total": total, "frames_processed": processed, "width": tk.w, "height": tk.h,
            "raw_track_ids": len(tk.tracks), "ms": int((time.time() - t0) * 1000)}
    return out, meta


def hud(img, unique, by_class):
    txt = f"UNIQUE {unique}  " + "  ".join(f"{PREFIX[k]} {v}" for k, v in sorted(by_class.items()))
    (tw, th), _ = cv2.getTextSize(txt, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
    cv2.rectangle(img, (10, 10), (24 + tw, 22 + th), (20, 20, 20), -1)
    cv2.putText(img, txt, (17, 15 + th), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 200, 255), 2, cv2.LINE_AA)

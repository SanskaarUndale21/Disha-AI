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


def _drop_rim_cracks(d):
    """A crack box that mostly overlaps a pothole box is the pothole's broken rim: drop it."""
    if not len(d):
        return d
    pot = d.xyxy[d.cls == CLS_ID["pothole"]]
    keep = np.ones(len(d), bool)
    if len(pot):
        for i in range(len(d)):
            if d.cls[i] != CLS_ID["pothole"] and _iou(d.xyxy[i], pot).max() > 0.5:
                keep[i] = False
    return d[keep]


def infer_batch(frames, cracks=None, conf_floor=None, imgsz=None):
    """Run the ensemble on several BGR frames at once (one batched GPU call per model). Returns one Dets per frame
    with unified class ids (config.CLASSES). Batching is what makes video analysis fast."""
    roles = _load()
    cracks = USE_CRACKS if cracks is None else cracks
    n = len(frames)
    acc = [([], [], []) for _ in range(n)]
    with _infer_lock:
        for r in roles:
            if r.role in ("cracks", "features") and not cracks:
                continue
            c = r.conf if conf_floor is None else min(r.conf, conf_floor)
            results = r.model.predict(list(frames), conf=c, iou=config.IOU_THRESHOLD, imgsz=imgsz or config.IMG_SIZE,
                                      quantize=16, verbose=False, batch=max(1, n))
            for k, res in enumerate(results):
                b = res.boxes
                if b is None or not len(b):
                    continue
                for xy, cf, cl in zip(b.xyxy.cpu().numpy(), b.conf.cpu().numpy(), b.cls.cpu().numpy().astype(int)):
                    name = r.cmap.get(int(cl))
                    if name is None:
                        continue
                    acc[k][0].append(xy)
                    acc[k][1].append(float(cf))
                    acc[k][2].append(CLS_ID[name])
    return [_drop_rim_cracks(Dets(*a)) for a in acc]


def infer(img, cracks=None, conf_floor=None, imgsz=None):
    """Run the ensemble on one BGR frame."""
    return infer_batch([img], cracks=cracks, conf_floor=conf_floor, imgsz=imgsz)[0]


FAR_PASS = os.getenv("RD_FAR_PASS", "1") != "0"


def _tiles(w, h, mode):
    """Overlapping crops (x1, y1, x2, y2) that magnify small, distant potholes. The old far pass enlarged one wide
    crop and then shrank it back to the detector size, so it gave no extra detail; these tiles are small enough
    that the detector sees them at 1.5 to 3 times the normal scale."""
    tw = 0.42 * w
    xs = [0.0, (w - tw) / 2, w - tw]
    th = 0.42 * w * 0.62
    if mode == "far":      # video: the band between the horizon and the middle of the road
        bands = [(0.27, 0.27 + th / h)]
    else:                  # photo: whole frame, two rows
        bands = [(0.12, 0.12 + th / h), (0.50, 0.50 + th / h)]
    out = []
    for b0, b1 in bands:
        y1, y2 = int(b0 * h), int(min(b1, 0.98) * h)
        if y2 - y1 < 64:
            y1, y2 = int(0.25 * h), int(0.7 * h)
        for x in xs:
            out.append((int(x), y1, int(x + tw), y2))
    return out


def _nms_same(d, thr=0.5):
    order = np.argsort(-d.conf)
    keep = []
    for i in order:
        if all(_iou(d.xyxy[i], d.xyxy[[k]])[0] < thr for k in keep):
            keep.append(int(i))
    return d[np.array(keep, int)]


def infer_tiles(frames, imgsz=None, mode="far"):
    """Pothole-only detections from magnified tiles, mapped back to full-frame coordinates. One batched call."""
    roles = [r for r in _load() if r.role == "pothole"]
    if not roles or not len(frames):
        return [Dets([], [], []) for _ in frames]
    crops, owners = [], []
    for fi, img in enumerate(frames):
        h, w = img.shape[:2]
        for (x1, y1, x2, y2) in _tiles(w, h, mode):
            c = img[y1:y2, x1:x2]
            if c.size:
                crops.append(c)
                owners.append((fi, x1, y1))
    acc = [([], []) for _ in frames]
    if crops:
        with _infer_lock:
            r = roles[0]
            results = r.model.predict(crops, conf=0.2, iou=config.IOU_THRESHOLD, imgsz=imgsz or config.IMG_SIZE,
                                      quantize=16, verbose=False, batch=min(12, max(1, len(crops))))
            for (fi, ox, oy), res in zip(owners, results):
                b = res.boxes
                if b is None or not len(b):
                    continue
                for xy, cf, cl in zip(b.xyxy.cpu().numpy(), b.conf.cpu().numpy(), b.cls.cpu().numpy().astype(int)):
                    if r.cmap.get(int(cl)) != "pothole":
                        continue
                    bx = xy.copy()
                    bx[[0, 2]] += ox
                    bx[[1, 3]] += oy
                    acc[fi][0].append(bx)
                    acc[fi][1].append(float(cf) * 0.95)  # tiny discount: a tile sees less context
    out = []
    for bx, cf in acc:
        d = Dets(bx, cf, [CLS_ID["pothole"]] * len(bx))
        out.append(_nms_same(d) if len(d) else d)
    return out


def infer_far(img, imgsz=None):
    """Single-frame far pass (live camera): horizon band tiles."""
    return infer_tiles([img], imgsz, "far")[0]


def merge_dets(a: Dets, b: Dets, iou_thr=0.45):
    """Union of two detection sets; overlapping same-class boxes keep the higher confidence."""
    if not len(b):
        return a
    if not len(a):
        return b
    keep_b = np.ones(len(b), bool)
    xyxy, conf, cls = list(a.xyxy), list(a.conf), list(a.cls)
    for i in range(len(b)):
        same = np.where(a.cls == b.cls[i])[0]
        if len(same):
            ov = _iou(b.xyxy[i], a.xyxy[same])
            j = same[int(ov.argmax())]
            if ov.max() > iou_thr:
                if b.conf[i] > conf[j]:
                    xyxy[j], conf[j] = b.xyxy[i], float(b.conf[i])
                keep_b[i] = False
    for i in np.where(keep_b)[0]:
        xyxy.append(b.xyxy[i]); conf.append(float(b.conf[i])); cls.append(b.cls[i])
    return Dets(np.array(xyxy), np.array(conf), np.array(cls))


HIGH_CONF = float(os.getenv("RD_HIGH_CONF", "0.40"))  # measured: precision 87% at this cut-off (models/confidence_levels.json)


def tier_for(conf):
    """high = right about 87% of the time on held-out day, night, fog and rain photos; otherwise possible."""
    return "high" if float(conf) >= HIGH_CONF else "possible"


def make_row(frame, cls, x1, y1, x2, y2, conf, track_id=None):
    h, w = frame.shape[:2]
    a = sevmod.analyze(frame, cls, x1, y1, x2, y2, conf)
    lane = scoring.lane_factor(((x1 + x2) / 2) / w)
    return {"class_name": cls, "confidence": round(float(conf), 4), "tier": tier_for(conf), "x1": float(x1), "y1": float(y1),
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
    if FAR_PASS:  # magnified tiles find small, far-away potholes the full-frame pass misses
        far = infer_tiles([proc], mode="photo")[0]
        ok = far.conf >= POTHOLE_CONF if len(far) else None
        if len(far) and ok.any():
            d = merge_dets(d, Dets(far.xyxy[ok], far.conf[ok], far.cls[ok]))
    rows = rows_from(img, d)
    return rows, {"enhanced": enhanced, "ms": int((time.time() - t0) * 1000)}


TRACK_ARGS = SimpleNamespace(tracker_type="bytetrack", track_high_thresh=0.22, track_low_thresh=0.08,
                             new_track_thresh=0.25, track_buffer=45, match_thresh=0.8, fuse_score=True)


class Tracker:
    """ByteTrack + per-track aggregation (majority class, best frame, crop). Used by video files and live mode."""

    def __init__(self, imgsz=None, far=True, allow=None):
        from ultralytics.trackers.byte_tracker import BYTETracker
        self.bt = BYTETracker(TRACK_ARGS)
        self.tracks = {}
        self.display = {}
        self.frame_idx = 0
        self.imgsz = imgsz
        self.far = far
        self.allow = set(allow) if allow else None
        self.w = self.h = 0

    def disp(self, tid):
        if tid not in self.display:
            self.display[tid] = len(self.display) + 1
        return self.display[tid]

    def step(self, frame, cracks=None, time_s=None, dets=None):
        """Detect + track one frame. Returns list of rows for the currently visible tracks.
        dets: detections already computed (batched video path); otherwise they are computed here."""
        self.h, self.w = frame.shape[:2]
        if dets is not None:
            proc, d = frame, dets
        else:
            proc, _ = preprocess(frame)
            d = infer(proc, cracks=cracks, conf_floor=0.1, imgsz=self.imgsz)
            if FAR_PASS and self.far and self.frame_idx % 2 == 0:
                self._far = infer_far(proc, self.imgsz)
            far = getattr(self, "_far", None)
            if FAR_PASS and self.far and far is not None and len(far):
                d = merge_dets(d, far)
        out = self.bt.update(d, proc) if len(d) else self.bt.update(Dets(np.zeros((0, 4)), [], []), proc)
        self.frame_idx += 1
        rows = []
        for x1, y1, x2, y2, tid, score, k, *_ in out:
            tid = int(tid)
            cls_now = config.CLASSES[int(k)]
            if self.allow and cls_now not in self.allow:
                continue
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
            if b.get("tier") != "high" and tr["hits"] >= 6 and float(b.get("confidence") or 0) >= 0.32:
                b["tier"] = "high"  # seen in many frames: repeat sightings count as confirmation
            rows.append(b)
        rows.sort(key=lambda r: r["track_id"])
        return rows


def label_track(r):
    tag = f'{PREFIX.get(r["class_name"], "RD")}#{r["display_id"]}' if r.get("display_id") else "..."
    return f'{tag} {r["severity"]} {r["confidence"]:.2f}'


VIDEO_QUALITY = {
    # 2K: faster. Frames above 2560 px are scaled down; detector input 640; far-road zoom pass off.
    "2k": {"max_side": 2560, "imgsz": 640, "far": False},
    # 4K: more detail. Frames up to 3840 px; detector input 960; far-road zoom pass on (finds distant potholes).
    "4k": {"max_side": 3840, "imgsz": 960, "far": True},
}


def normalize_quality(q):
    return "4k" if str(q or "").lower() in ("4k", "2160p", "uhd") else "2k"


VIDEO_BATCH = int(os.getenv("RD_VIDEO_BATCH", "6"))
MAX_PROCESS_FRAMES = int(os.getenv("RD_MAX_PROCESS_FRAMES", "650"))  # about 30 s of work on this laptop
VIDEO_BUDGET_S = float(os.getenv("RD_VIDEO_BUDGET_S", "36"))  # analysis target in seconds, uploads finish inside 45 s
SPARSE_EVERY = int(os.getenv("RD_SPARSE_EVERY", "3"))   # analyse 1 frame in N while nothing is seen
DENSE_FRAMES = int(os.getenv("RD_DENSE_FRAMES", "24"))   # then analyse every frame for this many frames


def detect_video(path, out_path, frame_cb=None, quality="2k", classes=None, falls=True):
    """Track defects through a video. Returns (unique track rows, meta). Annotated H.264 video is written.

    Speed: frames are read in chunks and run through the detector as one batch (far faster than frame by frame);
    magnified tiles that find distant potholes run on every third frame (every second in 4K); the person/fall check
    runs about 8 times per second. Every frame is analysed (stride 1) so tracks and confidence accumulate."""
    import imageio.v2 as iio

    cap = cv2.VideoCapture(str(path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    stride = max(1, config.VIDEO_FRAME_STRIDE)
    if total > MAX_PROCESS_FRAMES:  # long clips: analyse an evenly spaced subset so the wait stays short
        stride = max(stride, -(-total // MAX_PROCESS_FRAMES))
    writer = iio.get_writer(str(out_path), fps=fps / stride, codec="libx264", quality=7, macro_block_size=8,
                            ffmpeg_log_level="error", pixelformat="yuv420p")
    quality = normalize_quality(quality)
    cfg = VIDEO_QUALITY[quality]
    tile_every = 2 if quality == "4k" else 3
    tk = Tracker(imgsz=cfg["imgsz"], far=cfg["far"], allow=classes)
    idx = processed = 0
    t0 = time.time()
    fm, fall_list, last_pose = None, [], -1.0
    safety = None
    if falls:
        try:
            from . import safety
            fm = safety.FallMonitor()
        except Exception as e:
            print(f"[video] fall monitor unavailable: {e!r}")
            fm = None
    far_held = None
    last_shown, dense_left = [], 0
    sparse_every, hurry, tb = SPARSE_EVERY, False, None

    def read_chunk():
        nonlocal idx
        chunk = []
        while len(chunk) < VIDEO_BATCH:
            ok, frame = cap.read()
            if not ok:
                break
            if idx % stride:
                idx += 1
                continue
            if processed + len(chunk) >= config.VIDEO_MAX_FRAMES:
                break
            fh, fw = frame.shape[:2]
            if max(fh, fw) > cfg["max_side"]:
                sc = cfg["max_side"] / float(max(fh, fw))
                frame = cv2.resize(frame, (int(fw * sc) // 2 * 2, int(fh * sc) // 2 * 2), interpolation=cv2.INTER_AREA)
            chunk.append((idx, frame))
            idx += 1
        return chunk

    try:
        while True:
            chunk = read_chunk()
            if not chunk:
                break
            # adaptive sampling: while the road looks clear only every third frame is analysed; as soon as damage
            # shows up every frame is analysed for the next stretch, so tracks and confidence build quickly
            analyse = [k for k in range(len(chunk)) if (dense_left > 0 and not hurry) or k % sparse_every == 0]
            procs = {k: preprocess(chunk[k][1])[0] for k in analyse}
            dets_l = infer_batch([procs[k] for k in analyse], conf_floor=0.1, imgsz=cfg["imgsz"])
            dets = dict(zip(analyse, dets_l))
            want = [k for k in analyse if (chunk[k][0] // stride) % tile_every == 0] if FAR_PASS else []
            if want:
                far_res = infer_tiles([procs[k] for k in want], imgsz=cfg["imgsz"], mode="far")
                far_by = dict(zip(want, far_res))
            else:
                far_by = {}
            for k, (n, frame) in enumerate(chunk):
                if k in dets:
                    if k in far_by:
                        far_held = far_by[k]
                    d = dets[k]
                    if far_held is not None and len(far_held):
                        d = merge_dets(d, far_held)
                    rows = tk.step(procs[k], time_s=n / fps, dets=d)
                    shown = [r for r in rows if r["confirmed"]]
                    last_shown = shown
                    seen_damage = any(r.get("class_name") == "pothole" and float(r.get("confidence") or 0) >= 0.3 for r in rows)
                    dense_left = DENSE_FRAMES if seen_damage else max(0, dense_left - 1)
                else:
                    shown = last_shown
                    dense_left = max(0, dense_left - 1)
                ann = draw(frame, shown, label_track)
                hud(ann, len(tk.unique()), tk.by_class())
                t_s = n / fps
                if fm is not None and (t_s - last_pose >= 0.12 or last_pose < 0):
                    last_pose = t_s
                    try:
                        pots = [(r["track_id"], [r["x1"], r["y1"], r["x2"], r["y2"]]) for r in shown
                                if r.get("class_name") == "pothole" and r.get("track_id") is not None]
                        people, evs = fm.observe(t_s, safety.detect_people(frame), pots)
                        tk.people_last = people
                        for ev in evs:
                            url = safety.snapshot(ann, ev)
                            em = safety.record_emergency(ev, url)
                            fall_list.append({"id": em["id"], "time_s": round(t_s, 1), "snapshot_url": url, "message": em["message"]})
                    except Exception as e:
                        print(f"[video] fall check failed: {e!r}")
                for pp in getattr(tk, "people_last", []) or []:
                    x1, y1, x2, y2 = [int(v) for v in pp["box"]]
                    col = (48, 59, 255) if pp["fallen"] else (255, 255, 255)
                    cv2.rectangle(ann, (x1, y1), (x2, y2), col, 3 if pp["fallen"] else 1)
                    if pp["fallen"]:
                        cv2.putText(ann, "PERSON DOWN", (x1, max(18, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.8, col, 2, cv2.LINE_AA)
                writer.append_data(cv2.cvtColor(ann, cv2.COLOR_BGR2RGB))
                processed += 1
            if tb is None:
                tb = (time.time(), idx)  # start the budget clock after the first chunk (model warm-up is not counted)
            elif total and (idx - tb[1]) / max(1, total - tb[1]) > 0.08:
                # time budget: if the projected total exceeds it, analyse fewer frames so the user never waits long
                proj = (time.time() - tb[0]) / ((idx - tb[1]) / max(1, total - tb[1]))
                if proj > VIDEO_BUDGET_S:
                    hurry = True
                    sparse_every = min(12, sparse_every + 1)
                elif proj < VIDEO_BUDGET_S * 0.6:
                    hurry, sparse_every = False, max(SPARSE_EVERY, sparse_every - 1)
            if frame_cb and total:
                frame_cb(min(1.0, idx / total))
    finally:
        cap.release()
        writer.close()
    out = tk.final_rows()
    meta = {"fps": fps, "frames_total": total, "frames_processed": processed, "width": tk.w, "height": tk.h,
            "raw_track_ids": len(tk.tracks), "quality": quality, "falls": fall_list, "ms": int((time.time() - t0) * 1000)}
    return out, meta


def hud(img, unique, by_class):
    txt = f"UNIQUE {unique}  " + "  ".join(f"{PREFIX[k]} {v}" for k, v in sorted(by_class.items()))
    (tw, th), _ = cv2.getTextSize(txt, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
    cv2.rectangle(img, (10, 10), (24 + tw, 22 + th), (20, 20, 20), -1)
    cv2.putText(img, txt, (17, 15 + th), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 200, 255), 2, cv2.LINE_AA)

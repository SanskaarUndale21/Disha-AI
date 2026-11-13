"""Live patrol safety layer: lane marking condition (OpenCV only) and fall detection near potholes.

lane_status(frame)  -> {"status": good|faded|missing|unknown, "score", "coverage", "contrast", "segments"}
  Road region = lower 55% of the frame. Paint is found as bright, thin structures (white top-hat) that are
  either low saturation (white paint) or yellow hue; elongated components are kept and probabilistic Hough
  finds line segments at plausible lane angles (not near-horizontal). Segments are grouped into lines; each
  line's continuity = fraction of its visible span (inside the road region) that is painted. The score blends
  continuity with paint-vs-asphalt contrast. "unknown" is returned when the region does not look like road.

FallMonitor  pose model (Ultralytics yolo11n-pose, lazy, fp16 on CUDA) + IoU person tracking + fall rule:
  within 1.5 s the hip keypoints drop by > 25% of the earlier bbox height AND the body turns horizontal
  (bbox w/h > 1.1 or shoulder-hip line within 35 degrees of horizontal), then it stays down >= 0.5 s.
  A fall is an emergency when the person's feet (bbox bottom strip) overlap or lie within 0.5x the person's
  width of a confirmed pothole box. One emergency per person per 60 s.

Emergencies are kept in memory (GET /api/safety/emergencies). The alerts table is not used because the ops
alert scan auto-resolves any alert that is not tied to an active defect condition. "Notify emergency" is a
mock: a notification entry is recorded, no call is placed and no SMS is sent.
"""
import math
import threading
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

from . import config

# ---------------------------------------------------------------- lane markings
LANE_GOOD = 0.55
LANE_PRESENT = 0.18
_W = 640


def _cluster_lines(segs):
    """Group Hough segments into lines by angle and x position at the bottom of the road region."""
    groups = []
    for s in segs:
        x1, y1, x2, y2, ang, xb = s
        for g in groups:
            if abs(g["ang"] - ang) < 10 and abs(g["xb"] - xb) < 40:
                g["segs"].append(s)
                n = len(g["segs"])
                g["ang"] += (ang - g["ang"]) / n
                g["xb"] += (xb - g["xb"]) / n
                break
        else:
            groups.append({"ang": ang, "xb": xb, "segs": [s]})
    return groups


def _elongated(paint, w, min_area):
    """Keep elongated, solid, thin components (lane paint); drop blobs (cars, glare, gravel)."""
    n, lab, stats, _ = cv2.connectedComponentsWithStats(paint, connectivity=8)
    keep = np.zeros_like(paint)
    for i in range(1, n):
        x, y, bw, bh, area = stats[i]
        if area < min_area:
            continue
        comp = (lab[y:y + bh, x:x + bw] == i).astype(np.uint8)
        (_, _), (a, b), _ = cv2.minAreaRect(cv2.findNonZero(comp))
        L, T = max(a, b), max(1.0, min(a, b))
        if L / T < 3.0 or L < w * 0.03 or area / max(1.0, a * b) < 0.25 or T > w * 0.06:
            continue
        keep[y:y + bh, x:x + bw][comp > 0] = 255
    return keep


def lane_status(frame_bgr):
    H0, W0 = frame_bgr.shape[:2]
    sc = _W / W0 if W0 > _W else 1.0
    img = cv2.resize(frame_bgr, (round(W0 * sc), round(H0 * sc)), interpolation=cv2.INTER_AREA) if sc != 1.0 else frame_bgr
    h, w = img.shape[:2]
    y0 = int(h * 0.45)
    road = img[y0:]
    rh = road.shape[0]
    hsv = cv2.cvtColor(road, cv2.COLOR_BGR2HSV)
    Hc, S, V = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    gray = cv2.cvtColor(road, cv2.COLOR_BGR2GRAY)

    # road surface: grey or worn brown asphalt, not vegetation, not sky glare
    veg = (Hc >= 33) & (Hc <= 90) & (S > 40)
    asphalt = (S < 95) & (V > 35) & (V < 215) & ~veg
    asphalt_frac = float(asphalt.mean())
    out = {"status": "unknown", "score": 0.0, "coverage": 0.0, "contrast": 0.0, "segments": [],
           "asphalt": round(asphalt_frac, 3)}
    if asphalt_frac < 0.22:
        return out
    asphalt_v = float(np.median(gray[asphalt])) if asphalt.any() else 90.0

    # paint: brighter than its surroundings (top-hat), white (low S) or yellow hue
    k = max(9, int(w * 0.035)) | 1
    tophat = cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, cv2.getStructuringElement(cv2.MORPH_RECT, (k, k)))
    white = (S < 70) & (V > max(110, asphalt_v + 25))
    # yellow paint is often not brighter than asphalt, but it is more saturated than its surroundings
    sat_hat = cv2.morphologyEx(S, cv2.MORPH_TOPHAT, cv2.getStructuringElement(cv2.MORPH_RECT, (k, k)))
    yellow = (Hc >= 12) & (Hc <= 34) & (S > 45) & (V > 50) & (sat_hat > 20)
    min_area = max(12, int(w * h * 0.00004))
    keep = np.zeros(gray.shape, np.uint8)
    for m in ((tophat > 18) & white, yellow):  # white and yellow separately so noise in one cannot spoil the other
        paint = cv2.morphologyEx(m.astype(np.uint8) * 255, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
        keep |= _elongated(paint, w, min_area)

    lines = cv2.HoughLinesP(keep, 1, np.pi / 180, threshold=18, minLineLength=max(12, int(w * 0.035)),
                            maxLineGap=int(w * 0.02))
    segs = []
    if lines is not None:
        for x1, y1, x2, y2 in lines.reshape(-1, 4):
            ang = math.degrees(math.atan2(y2 - y1, x2 - x1))
            ang = ang + 180 if ang < 0 else ang  # 0..180
            if min(ang, 180 - ang) < 18:  # near-horizontal: crossings, shadows, kerbs far away
                continue
            dy = (y2 - y1) or 1e-6
            xb = x1 + (rh - 1 - y1) * (x2 - x1) / dy
            xh = x1 + (-0.06 * h - y1) * (x2 - x1) / dy  # x where the line meets the horizon (approx.)
            if not (-0.25 * w <= xh <= 1.25 * w):  # lane lines converge towards the vanishing point
                continue
            if abs(90 - ang) < 6 and min(y1, y2) < rh * 0.12 and abs((x1 + x2) / 2 - w / 2) > 0.2 * w:
                continue  # pole or post rising out of the road region
            segs.append((int(x1), int(y1), int(x2), int(y2), ang, xb))
    if not segs:
        out.update(status="missing")
        return out

    dil = cv2.dilate(keep, np.ones((5, 5), np.uint8))
    groups = _cluster_lines(segs)
    # zebra crossings / painted text: several short parallel groups side by side in the same rows
    short = []
    for g in groups:
        ys_ = [v for s_ in g["segs"] for v in (s_[1], s_[3])]
        g["yr"] = (min(ys_), max(ys_))
        if g["yr"][1] - g["yr"][0] < rh * 0.3:
            short.append(g)
    zebra = set()
    for g in short:
        band = [o for o in short if min(g["yr"][1], o["yr"][1]) - max(g["yr"][0], o["yr"][0]) > 0.5 * (g["yr"][1] - g["yr"][0])]
        if len(band) >= 4:
            zebra.update(id(o) for o in band)
    lines_out = []
    for g in groups:
        if id(g) in zebra or g["yr"][1] - g["yr"][0] < rh * 0.25:
            continue  # zebra stripe, or too little vertical extent to be a lane line (puddle rims, cracks)
        pts = np.array([[s[0], s[1]] for s in g["segs"]] + [[s[2], s[3]] for s in g["segs"]], np.float32)
        if np.ptp(pts[:, 1]) < 4:
            continue
        a, b = np.polyfit(pts[:, 1], pts[:, 0], 1)  # x = a*y + b
        ys = np.arange(0, rh, 2)
        xs = a * ys + b
        inside = (xs >= 0) & (xs < w)
        if inside.sum() < rh * 0.15 / 2:
            continue
        ys_i, xs_i = ys[inside], xs[inside].astype(int)
        cont = float((dil[ys_i, xs_i] > 0).mean())
        # contrast: paint pixels on this line vs the asphalt median
        on = keep[ys_i, xs_i] > 0
        pv = float(np.median(gray[ys_i[on], xs_i[on]])) if on.any() else asphalt_v
        contrast = max(0.0, pv - asphalt_v)
        painted = float(sum(math.hypot(s[2] - s[0], s[3] - s[1]) for s in g["segs"]))
        lines_out.append({"cont": cont, "contrast": contrast, "painted": painted, "segs": g["segs"],
                          "span": [int(ys_i[0]), int(ys_i[-1])], "fit": (a, b)})
    if not lines_out:
        out.update(status="missing")
        return out
    lines_out.sort(key=lambda L: L["cont"] * (0.5 + min(1.0, L["contrast"] / 60)), reverse=True)
    best = lines_out[:2]
    cont = float(np.mean([L["cont"] for L in best]))
    contrast = float(np.mean([L["contrast"] for L in best]))
    # dashed lines cover ~30-45% of their span; solid lines ~90%. 0.45 continuity counts as fully continuous.
    cont_n = min(1.0, cont / 0.45)
    con_n = min(1.0, contrast / 70)
    score = round(0.6 * cont_n + 0.4 * con_n, 3) if cont > 0.06 else round(0.3 * cont_n * con_n, 3)
    if score >= LANE_GOOD:
        status = "good"
    elif score >= LANE_PRESENT:
        status = "faded"
    else:
        status = "missing"
    segs_out = []
    for L in sorted(lines_out, key=lambda L: -L["painted"]):
        for s in sorted(L["segs"], key=lambda s: -math.hypot(s[2] - s[0], s[3] - s[1])):
            segs_out.append([round(s[0] / sc, 1), round((s[1] + y0) / sc, 1), round(s[2] / sc, 1), round((s[3] + y0) / sc, 1)])
    out.update(status=status, score=score, coverage=round(cont, 3), contrast=round(contrast, 1),
               segments=segs_out[:12] if status != "missing" else [])
    return out


class LaneSmoother:
    """Rolling median over the last n results so the chip does not flicker."""

    def __init__(self, n=15):
        self.hist = deque(maxlen=n)
        self.last = None

    def push(self, r):
        self.hist.append(r)
        self.last = r

    def value(self):
        if not self.hist:
            return None
        known = [r for r in self.hist if r["status"] != "unknown"]
        if len(known) * 2 < len(self.hist):
            return {"status": "unknown", "score": 0.0, "segments": self.last["segments"] if self.last else []}
        sc = float(np.median([r["score"] for r in known]))
        missing = sum(r["status"] == "missing" for r in known)
        if missing * 2 > len(known):
            st = "missing"
        else:
            st = "good" if sc >= LANE_GOOD else "faded" if sc >= LANE_PRESENT else "missing"
        return {"status": st, "score": round(sc, 3), "segments": self.last["segments"] if self.last else []}


# ---------------------------------------------------------------- pose model (shared, lazy)
POSE_WEIGHTS = config.ROOT / "yolo11n-pose.pt"
_pose = None
_pose_dev = None
_pose_err = None
_pose_lock = threading.Lock()


def pose_model():
    global _pose, _pose_dev, _pose_err
    if _pose is not None or _pose_err is not None:
        return _pose
    with _pose_lock:
        if _pose is None and _pose_err is None:
            try:
                import torch
                from ultralytics import YOLO
                dev = "cpu"
                if torch.cuda.is_available():
                    free, _tot = torch.cuda.mem_get_info()
                    dev = 0 if free > 700 * 1024 * 1024 else "cpu"  # GPU is shared: fall back to CPU when tight
                m = YOLO(str(POSE_WEIGHTS) if POSE_WEIGHTS.exists() else "yolo11n-pose.pt")
                if not POSE_WEIGHTS.exists():
                    try:  # keep the downloaded weights at the repo root next to the other base weights
                        import shutil
                        src = getattr(m, "ckpt_path", None)
                        if src and Path(src).exists() and Path(src).resolve() != POSE_WEIGHTS.resolve():
                            shutil.move(str(src), POSE_WEIGHTS)
                    except Exception:
                        pass
                _pose, _pose_dev = m, dev
            except Exception as e:  # no network / no weights: fall detection is disabled, live keeps working
                _pose_err = repr(e)
                print(f"[safety] pose model unavailable: {_pose_err}")
    return _pose


def detect_people(frame, conf=0.3, imgsz=640):
    """[{box:[x1,y1,x2,y2], conf, kps: 17x3 list}] for people in a BGR frame."""
    m = pose_model()
    if m is None:
        return []
    r = m.predict(frame, conf=conf, imgsz=imgsz, device=_pose_dev, verbose=False,
                  **({"quantize": 16} if _pose_dev != "cpu" else {}),
                  classes=[0])[0]
    out = []
    if r.boxes is None or not len(r.boxes):
        return out
    boxes = r.boxes.xyxy.cpu().numpy()
    confs = r.boxes.conf.cpu().numpy()
    kps = r.keypoints.data.cpu().numpy() if r.keypoints is not None else None
    for i in range(len(boxes)):
        out.append({"box": [float(v) for v in boxes[i]], "conf": float(confs[i]),
                    "kps": kps[i].tolist() if kps is not None else None})
    return out


# ---------------------------------------------------------------- road hazards (COCO model)
HAZARD_CLASSES = {16: ("animal", "Dog on road"), 17: ("animal", "Horse on road"), 18: ("animal", "Sheep on road"),
                  19: ("animal", "Cow on road"), 20: ("animal", "Elephant on road"), 11: ("sign", "Stop sign"),
                  9: ("signal", "Traffic light")}
_haz = None
_haz_err = None


def hazard_model():
    global _haz, _haz_err
    if _haz is None and _haz_err is None:
        try:
            from ultralytics import YOLO
            w = config.ROOT / "yolo11s.pt"
            _haz = YOLO(str(w if w.exists() else "yolo11s.pt"))
        except Exception as e:
            _haz_err = e
            print(f"[safety] hazard model unavailable: {e!r}")
    return _haz


def detect_hazards(frame, conf=0.35, imgsz=512):
    """Road-safety objects: animals on the road, stop signs, traffic lights. [{box, kind, label, conf}]"""
    m = hazard_model()
    if m is None:
        return []
    r = m.predict(frame, conf=conf, imgsz=imgsz, verbose=False, classes=list(HAZARD_CLASSES),
                  **({"quantize": 16} if _pose_dev != "cpu" else {}))[0]
    out = []
    if r.boxes is None or not len(r.boxes):
        return out
    for b, c, k in zip(r.boxes.xyxy.cpu().numpy(), r.boxes.conf.cpu().numpy(), r.boxes.cls.cpu().numpy().astype(int)):
        kind, label = HAZARD_CLASSES[int(k)]
        out.append({"box": [float(v) for v in b], "kind": kind, "label": label, "conf": round(float(c), 2)})
    return out


# ---------------------------------------------------------------- fall logic
FALL_WINDOW_S = 1.5
FALL_HOLD_S = 0.5
FALL_DROP = 0.25
FALL_COOLDOWN_S = 60.0
LYING_HOLD_S = 1.5  # a person already lying still this long counts as down
KP_CONF = 0.3


def _iou(a, b):
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    u = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / u if u > 0 else 0.0


def _rect_dist(a, b):
    dx = max(0.0, max(a[0], b[0]) - min(a[2], b[2]))
    dy = max(0.0, max(a[1], b[1]) - min(a[3], b[3]))
    return math.hypot(dx, dy)


def _mid(kps, i, j):
    if kps is None:
        return None
    pts = [kps[k] for k in (i, j) if kps[k][2] >= KP_CONF]
    if not pts:
        return None
    return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))


def posture(p):
    """(hip_y, horizontal) for a person {box, kps}."""
    x1, y1, x2, y2 = p["box"]
    w, h = x2 - x1, max(1.0, y2 - y1)
    kps = p.get("kps")
    hip = _mid(kps, 11, 12)
    sh = _mid(kps, 5, 6)
    hip_y = hip[1] if hip else y1 + 0.55 * h
    horizontal = w / h > 1.1
    if hip and sh:
        ang = abs(math.degrees(math.atan2(hip[1] - sh[1], hip[0] - sh[0])))
        ang = min(ang, 180 - ang)  # angle from horizontal
        if ang <= 35:
            horizontal = True
    return hip_y, horizontal


class _Person:
    def __init__(self, pid, p, t):
        self.id = pid
        self.box = p["box"]
        self.hist = deque()  # (t, box, hip_y, horizontal)
        self.last_t = t
        self.down_since = None  # candidate fall start
        self.horiz_since = None  # when the body first became horizontal (for people found already lying down)
        self.fallen = False
        self.last_alert = -1e9


class FallMonitor:
    def __init__(self):
        self.people: dict[int, _Person] = {}
        self.next_id = 1
        self.potholes = {}  # pothole display id -> (t_last_seen, box)

    def _match(self, dets, t):
        pairs = []
        for pid, P in self.people.items():
            pw, ph = P.box[2] - P.box[0], P.box[3] - P.box[1]
            pb = ((P.box[0] + P.box[2]) / 2, P.box[3])
            for j, d in enumerate(dets):
                iou = _iou(P.box, d["box"])
                db = ((d["box"][0] + d["box"][2]) / 2, d["box"][3])
                near = math.hypot(pb[0] - db[0], pb[1] - db[1]) < 0.75 * max(pw, ph)
                if iou > 0.1 or near:
                    pairs.append((iou + (0.05 if near else 0), pid, j))
        pairs.sort(reverse=True)
        used_p, used_d, out = set(), set(), {}
        for _, pid, j in pairs:
            if pid in used_p or j in used_d:
                continue
            used_p.add(pid)
            used_d.add(j)
            out[j] = pid
        return out

    def _near_pothole(self, box, t):
        x1, y1, x2, y2 = box
        pw, ph = x2 - x1, y2 - y1
        feet = [x1, y2 - 0.2 * ph, x2, y2]
        best = None
        for pid, (ts, pb) in self.potholes.items():
            if t - ts > 2.0:
                continue
            d = _rect_dist(feet, pb)
            if d <= 0.5 * pw and (best is None or d < best[1]):
                best = (pid, d, pb)
        return best

    def observe(self, t, dets, potholes=()):
        """Update with one frame. dets: [{box, kps}], potholes: [(display_id, box)] confirmed tracks.
        Returns (people, events): people = [{id, box, fallen}], events = confirmed falls near potholes."""
        for pid, box in potholes:
            self.potholes[pid] = (t, list(box))
        for pid in [k for k, (ts, _) in self.potholes.items() if t - ts > 5.0]:
            del self.potholes[pid]
        match = self._match(dets, t)
        seen = set()
        for j, d in enumerate(dets):
            pid = match.get(j)
            if pid is None:
                pid = self.next_id
                self.next_id += 1
                self.people[pid] = _Person(pid, d, t)
            P = self.people[pid]
            seen.add(pid)
            P.box, P.last_t = d["box"], t
            hip_y, horiz = posture(d)
            P.hist.append((t, d["box"], hip_y, horiz))
            while P.hist and t - P.hist[0][0] > FALL_WINDOW_S + FALL_HOLD_S + 0.5:
                P.hist.popleft()
        for pid in [k for k, P in self.people.items() if t - P.last_t > 2.0]:
            del self.people[pid]

        events = []
        for pid in seen:
            P = self.people[pid]
            _, box, hip_y, horiz = P.hist[-1]
            P.horiz_since = (P.horiz_since if P.horiz_since is not None else t) if horiz else None
            if P.down_since is None:
                if horiz and t - P.horiz_since >= LYING_HOLD_S and len(P.hist) >= 3:
                    c0 = ((P.hist[0][1][0] + P.hist[0][1][2]) / 2, (P.hist[0][1][1] + P.hist[0][1][3]) / 2)
                    c1 = ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)
                    if math.hypot(c1[0] - c0[0], c1[1] - c0[1]) < 0.6 * max(1.0, box[2] - box[0]):
                        P.down_since = P.horiz_since  # lying still on the road: person down
                if horiz and P.down_since is None:
                    for (tp, bp, hy, hz) in P.hist:
                        if hz or t - tp > FALL_WINDOW_S:
                            continue
                        hp = max(1.0, bp[3] - bp[1])
                        if hip_y - hy > FALL_DROP * hp:
                            P.down_since = t
                            break
            elif not horiz:
                P.down_since, P.fallen = None, False  # got up: cancel
            if P.down_since is not None and t - P.down_since >= FALL_HOLD_S:
                if not P.fallen:
                    P.fallen = True
                    near = self._near_pothole(box, t)
                    if t - P.last_alert >= FALL_COOLDOWN_S:
                        P.last_alert = t
                        events.append({"person_id": pid, "box": box, "pothole_id": near[0] if near else None,
                                       "pothole_box": near[2] if near else None})
        people = [{"id": P.id, "box": [round(v, 1) for v in P.box], "fallen": P.fallen}
                  for P in self.people.values() if P.last_t == t]
        return people, events

    def update(self, frame, potholes=(), t=None):
        return self.observe(time.time() if t is None else t, detect_people(frame), potholes)


# ---------------------------------------------------------------- emergencies (in memory)
EMERGENCIES: list = []
_em_lock = threading.Lock()
_em_seq = 0
MOCK_TO = "Emergency 112 (mock, not dialled)"


def snapshot(frame, ev):
    img = frame.copy()
    if ev.get("pothole_box"):
        x1, y1, x2, y2 = [int(v) for v in ev["pothole_box"]]
        cv2.rectangle(img, (x1, y1), (x2, y2), (48, 59, 255), 2)
        cv2.putText(img, f"PH {ev['pothole_id']}", (x1, max(14, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (48, 59, 255), 2)
    x1, y1, x2, y2 = [int(v) for v in ev["box"]]
    cv2.rectangle(img, (x1, y1), (x2, y2), (32, 45, 217), 3)
    cv2.putText(img, "FALL", (x1, max(14, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (32, 45, 217), 2)
    name = f"fall_{uuid.uuid4().hex}.jpg"
    cv2.imwrite(str(config.ANNOTATED / name), img, [cv2.IMWRITE_JPEG_QUALITY, 88])
    return f"/media/annotated/{name}"


def record_emergency(ev, snapshot_url, lat=None, lon=None):
    global _em_seq
    msg = f"Fall detected near pothole PH {ev['pothole_id']}" if ev["pothole_id"] is not None else "Person down detected on the road"
    if lat is not None and lon is not None:
        msg += f" at {lat:.5f}, {lon:.5f}"
    with _em_lock:
        _em_seq += 1
        em = {"id": _em_seq, "type": "fall", "level": "critical", "pothole_id": ev["pothole_id"], "message": msg,
              "snapshot_url": snapshot_url, "lat": lat, "lon": lon, "status": "open",
              "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "notifications": [{"to": MOCK_TO, "message": msg + ". Ambulance requested (mock).",
                                 "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}]}
        EMERGENCIES.append(em)
        del EMERGENCIES[:-200]
    from . import events
    events.publish("emergency.fall", {k: em[k] for k in ("id", "type", "level", "pothole_id", "message",
                                                         "snapshot_url", "lat", "lon", "created_at")}, audience="all")
    return em


def register(app):
    from fastapi import Depends, HTTPException

    from . import auth, events

    @app.get("/api/safety/emergencies")
    def emergencies(status: str = "all", _u=Depends(auth.require_officer)):
        with _em_lock:
            rows = [e for e in EMERGENCIES if status == "all" or e["status"] == status]
        return list(reversed(rows))

    @app.post("/api/safety/emergencies/{eid}/ack")
    def emergency_ack(eid: int, user=Depends(auth.require_officer)):
        with _em_lock:
            em = next((e for e in EMERGENCIES if e["id"] == eid), None)
            if em is None:
                raise HTTPException(404, "emergency not found")
            em["status"] = "acknowledged"
            em["acknowledged_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            em["acknowledged_by"] = (user or {}).get("email") if isinstance(user, dict) else None
        events.publish("emergency.updated", {"id": eid, "status": "acknowledged"})
        return em

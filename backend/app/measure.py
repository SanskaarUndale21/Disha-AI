"""Pothole size and depth measurement from a single photo.

Method
1. Detection. detector.detect_image gives each pothole a box and a traced damaged outline (polygon, OpenCV
   segmentation in severity.py). Every pothole row is measured. An explicit box can also be passed.
2. Scale (metres per pixel), best available source, reported with its uncertainty:
   a. Reference object (A4 sheet, credit card, 500 ml bottle, shoe/foot or a custom length) marked with a box:
      m/px = real length / long side of the box in pixels. About plus or minus 10 percent.
   b. Ground-plane geometry with a pitched camera: camera height 1.2 m (phone) or 1.4 m (dashcam), horizontal field
      of view about 66 degrees across the long side of the image, f = (long side / 2) / tan(33 deg). The horizon
      row y_h comes from the depth model itself (on a flat road inverse depth is linear in the image row and zero at
      the horizon, so a line fit to the lower half of the central-column profile gives y_h, accepted when R2 is at
      least 0.9), else from road-edge Hough lines, else 40 percent of the height. The camera pitch follows from
      y_h: tan(pitch) = (cy - y_h) / f. A ground point at normalised row y_n has optical depth
      Z = H / (y_n cos(pitch) + sin(pitch)) and road coordinates (X, F) = (x_n Z, Z (cos(pitch) - y_n sin(pitch))).
      Every outline vertex is mapped onto the road plane, so far edges are not under-measured. Plus or minus 30
      percent (45 percent when the horizon is only a fallback guess).
   c. Close-up with no usable horizon (box above 25 percent of the frame): the frame width is assumed to show
      about 2 m of road. Plus or minus 60 percent.
3. Width, length, area. cv2.minAreaRect of the outline on the road plane (or pixels x m/px): width = shorter side,
   length = longer side, area = shoelace area of the outline. Fallback outline: an ellipse inside the box.
4. Depth. Depth Anything V2 Small (Apache-2.0, depth-anything/Depth-Anything-V2-Small-hf), long side 518, gives
   relative inverse depth D. A plane is fitted (least squares with outlier rejection) to a ring of road just
   outside the outline. A floor point below the road on the same camera ray satisfies D_plane / D = Z' / Z, so
   depth below the road = H (D_plane / D - 1) in ground-plane mode and Zc (D_plane / D - 1) with Zc = m/px x f
   otherwise. Capped at 0.35 x width and 30 cm. Max depth = 95th percentile inside the outline, mean = mean.
   The result is only used when the drop is clearly above the road-ring noise (p90 of the drop above 3 sigma,
   mean above 1 sigma, p90 at least 2 percent of the depth). The small model smooths away dents of a few cm, so this
   often fails. Then depth is flagged not reliable and replaced by an estimate from typical proportions: 5 to 20
   percent of width, scaled by the detector's dark-contrast depth index, with that range reported. Standing water
   reflects, so depth is underestimated when water is detected.
5. Volume = mean depth x area (litres = m3 x 1000). Cold mix kg = volume m3 x 2300 kg/m3 x 1.1 compaction.
6. Annotated image: outline, minimum-area rectangle with width and length labels in cm and a small depth inset.
"""
import hashlib
import os
import math
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from fastapi import File, Form, HTTPException, UploadFile

from . import config, detector
from .db import Detection, Inspection, SessionLocal

DEPTH_MODEL_ID = "depth-anything/Depth-Anything-V2-Small-hf"
DEPTH_LONG_SIDE = 518
FOV_DEG = 66.0
H_PHONE, H_DASH = 1.2, 1.4
CLOSEUP_FRAME_M = 2.0
DEPTH_WIDTH_CAP = 0.35
PRIOR_RATIO = (0.05, 0.20)
REFERENCES_CM = {"a4": 29.7, "credit_card": 8.56, "bottle_500ml": 21.0, "foot": 27.0}
REFERENCE_WORDS = {"a4": "A4 sheet", "credit_card": "credit card", "bottle_500ml": "500 ml bottle",
                   "foot": "shoe or foot", "custom": "custom reference"}
MODE_WORDS = {"reference": "Measured against the reference object you marked",
              "ground_plane": "Estimated from camera height and perspective",
              "closeup": "Close-up photo: assumes about 2 m of road across the frame",
              "box": "Box supplied by the request"}
SCALE_UNC = {"reference": 10, "ground_plane": 30, "ground_fallback": 45, "closeup": 60}
DEPTH_UNC = {"reference": 30, "ground_plane": 45, "closeup": 60}
DEPTH_CONF = {"reference": "high", "ground_plane": "medium", "closeup": "low"}
ASPHALT_KG_M3, COMPACTION = 2300.0, 1.1

_lock = threading.Lock()
_depth = {"model": None, "device": None, "dtype": None}
_cache: "OrderedDict[str, dict]" = OrderedDict()
CACHE_MAX = 64


# ---------------------------------------------------------------- depth model
def _load_depth():
    if _depth["model"] is not None:
        return _depth
    import torch
    from transformers import AutoModelForDepthEstimation
    dev, dt = "cpu", torch.float32
    if torch.cuda.is_available():
        try:
            free, _ = torch.cuda.mem_get_info()
            if free > 700 * 1024 * 1024:
                dev, dt = "cuda", torch.float16
        except Exception:
            pass
    last = None
    for kw in ({"local_files_only": True}, {}):  # cached weights load fast and without network
        for dk in ("dtype", "torch_dtype"):
            try:
                m = AutoModelForDepthEstimation.from_pretrained(DEPTH_MODEL_ID, **{dk: dt}, **kw)
                break
            except TypeError as e:
                last = e
            except OSError as e:
                last = e
                m = None
                break
        else:
            m = None
        if m is not None:
            break
    if m is None:
        raise RuntimeError(f"Could not load the depth model: {last}")
    m = m.to(dev).eval()
    _depth.update(model=m, device=dev, dtype=dt)
    return _depth


def depth_map(img):
    """Relative inverse depth (bigger = closer) at the image's own resolution."""
    import torch
    h, w = img.shape[:2]
    s = DEPTH_LONG_SIDE / max(h, w)
    nh, nw = max(14, int(round(h * s / 14)) * 14), max(14, int(round(w * s / 14)) * 14)
    rgb = cv2.cvtColor(cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2RGB)
    x = (rgb.astype(np.float32) / 255.0 - np.array([0.485, 0.456, 0.406], np.float32)) / np.array(
        [0.229, 0.224, 0.225], np.float32)
    with _lock:
        d = _load_depth()
        t = torch.from_numpy(x.transpose(2, 0, 1)[None]).to(d["device"], d["dtype"])
        with torch.inference_mode():
            out = d["model"](pixel_values=t).predicted_depth
        pred = out.float().squeeze().cpu().numpy()
        del t, out
        if d["device"] == "cuda":
            torch.cuda.empty_cache()
    return cv2.resize(pred, (w, h), interpolation=cv2.INTER_CUBIC)


# ---------------------------------------------------------------- geometry
def find_horizon(img):
    """Vanishing point row of road edges via Hough lines. Returns (y_h, found)."""
    h, w = img.shape[:2]
    s = 960 / max(h, w) if max(h, w) > 960 else 1.0
    g = cv2.cvtColor(cv2.resize(img, (int(w * s), int(h * s))) if s < 1 else img, cv2.COLOR_BGR2GRAY)
    sh, sw = g.shape
    e = cv2.Canny(cv2.GaussianBlur(g, (5, 5), 0), 60, 160)
    e[: int(sh * 0.3)] = 0
    lines = cv2.HoughLinesP(e, 1, np.pi / 180, 60, minLineLength=int(0.12 * max(sh, sw)), maxLineGap=12)
    if lines is None:
        return 0.4 * h, False
    left, right = [], []
    for x1, y1, x2, y2 in lines.reshape(-1, 4).tolist():
        ang = math.degrees(math.atan2(y2 - y1, x2 - x1))
        a = abs(ang) % 180
        a = min(a, 180 - a)
        if not 18 <= a <= 72:
            continue
        ln = math.hypot(x2 - x1, y2 - y1)
        # image y grows down: a road edge on the left rises to the right (negative slope)
        (left if (y2 - y1) * (x2 - x1) < 0 else right).append((ln, x1, y1, x2, y2))
    left = sorted(left, reverse=True)[:25]
    right = sorted(right, reverse=True)[:25]
    ys = []
    for _, a1, b1, a2, b2 in left:
        for _, c1, d1, c2, d2 in right:
            den = (a1 - a2) * (d1 - d2) - (b1 - b2) * (c1 - c2)
            if abs(den) < 1e-6:
                continue
            px = ((a1 * b2 - b1 * a2) * (c1 - c2) - (a1 - a2) * (c1 * d2 - d1 * c2)) / den
            py = ((a1 * b2 - b1 * a2) * (d1 - d2) - (b1 - b2) * (c1 * d2 - d1 * c2)) / den
            if 0.12 * sh <= py <= 0.62 * sh and -0.2 * sw <= px <= 1.2 * sw:
                ys.append(py)
    if len(ys) < 4:
        return 0.4 * h, False
    q1, med, q3 = np.percentile(ys, [25, 50, 75])
    if q3 - q1 > 0.12 * sh:
        return 0.4 * h, False
    return float(med / s), True


def focal_px(w, h):
    return (max(w, h) / 2.0) / math.tan(math.radians(FOV_DEG / 2))


def horizon_from_depth(D):
    """Horizon row from the depth model: on a flat road inverse depth grows linearly with the image row and is
    zero at the horizon. Fit the central-column median profile of the lower half. Returns (y_h, r2) or (None, r2)."""
    h, w = D.shape
    prof = np.median(D[:, int(0.25 * w):int(0.75 * w)], axis=1).astype(np.float64)
    ys = np.arange(h, dtype=np.float64)
    keep = ys >= 0.45 * h
    p = None
    for _ in range(4):
        if keep.sum() < 10:
            return None, 0.0
        p = np.polyfit(ys[keep], prof[keep], 1)
        r = prof - np.polyval(p, ys)
        sd = 1.4826 * np.median(np.abs(r[keep] - np.median(r[keep]))) + 1e-6
        keep = (ys >= 0.45 * h) & (np.abs(r) < 2.5 * sd)
    sel = ys >= 0.45 * h
    ss_res = float(np.sum((prof[sel] - np.polyval(p, ys[sel])) ** 2))
    ss_tot = float(np.sum((prof[sel] - prof[sel].mean()) ** 2)) + 1e-9
    r2 = 1 - ss_res / ss_tot
    if p[0] <= 0:
        return None, r2
    yh = -p[1] / p[0]
    if not (-1.5 * h <= yh <= 0.75 * h):
        return None, r2
    return float(yh), r2


def _pitch(yh, h, f):
    return math.atan2((h / 2.0) - yh, f)  # camera pitched down by this angle, radians


def to_ground(pts, w, h, yh, f, H):
    """Image points -> road-plane metres (X to the right, F forward) for a camera H metres above a flat road,
    pitched down so that the horizon falls on row yh. Z along the optical axis is H / (y_n cos t + sin t)."""
    p = np.asarray(pts, np.float64)
    t = _pitch(yh, h, f)
    xn, yn = (p[:, 0] - w / 2.0) / f, (p[:, 1] - h / 2.0) / f
    den = np.maximum(yn * math.cos(t) + math.sin(t), 0.02)
    Z = H / den
    return np.stack([xn * Z, Z * (math.cos(t) - yn * math.sin(t))], 1), Z


def from_ground(g, w, h, yh, f, H):
    t = _pitch(yh, h, f)
    g = np.asarray(g, np.float64)
    X, F = g[:, 0], g[:, 1]
    Py = -F * math.sin(t) + H * math.cos(t)
    Pz = np.maximum(F * math.cos(t) + H * math.sin(t), 1e-3)
    return np.stack([w / 2.0 + f * X / Pz, h / 2.0 + f * Py / Pz], 1)


def shoelace(p):
    x, y = p[:, 0], p[:, 1]
    return 0.5 * abs(float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))))


def outline(row, w, h):
    polys = [np.array(p, np.float64) for p in (row.get("polygon") or []) if len(p) >= 3]
    if polys:
        return polys, "traced outline"
    x1, y1, x2, y2 = row["x1"], row["y1"], row["x2"], row["y2"]
    t = np.linspace(0, 2 * np.pi, 32, endpoint=False)
    e = np.stack([(x1 + x2) / 2 + 0.4 * (x2 - x1) * np.cos(t), (y1 + y2) / 2 + 0.4 * (y2 - y1) * np.sin(t)], 1)
    return [e], "ellipse inside the box"


def _plane_fit(xs, ys, vs):
    A = np.stack([np.ones_like(xs), xs, ys], 1)
    keep = np.ones(len(vs), bool)
    coef = np.zeros(3)
    for _ in range(4):
        if keep.sum() < 12:
            break
        coef, *_ = np.linalg.lstsq(A[keep], vs[keep], rcond=None)
        r = vs - A @ coef
        mad = np.median(np.abs(r[keep] - np.median(r[keep]))) + 1e-9
        keep = np.abs(r) < 2.5 * 1.4826 * mad
    return coef, keep


# ---------------------------------------------------------------- core
def _measure_one(img, D, row, idx, scale, notes_common):
    h, w = img.shape[:2]
    polys, src = outline(row, w, h)
    pts = np.vstack(polys)
    mode = scale["mode"]
    notes = list(notes_common)
    if src != "traced outline":
        notes.append("Outline not traced, an ellipse inside the box was used.")
    f, H, yh = scale["f"], scale["H"], scale["yh"]

    # ---------- size
    corners = None
    size_ok = True
    if mode == "ground_plane":
        g_polys = [to_ground(p, w, h, yh, f, H)[0] for p in polys]
        gp = np.vstack(g_polys).astype(np.float32)
        (gcx, gcy), (a, b), ang = cv2.minAreaRect(gp)
        wid, lng = min(a, b), max(a, b)
        area = sum(shoelace(g) for g in g_polys)
        ok = 0.04 <= wid <= 2.5 and lng <= 4.0 and float(pts[:, 1].min()) > yh + 0.02 * h
        corners = from_ground(cv2.boxPoints(((gcx, gcy), (a, b), ang)), w, h, yh, f, H)
        zc = float(np.median(to_ground(pts, w, h, yh, f, H)[1]))
        if not ok:
            size_ok = False
            notes.append("Size not reliable: the outline is very far away or covers merged damage, so the "
                         "perspective geometry gives an extreme value.")
    if mode != "ground_plane":
        mpp = scale["mpp"]
        (cx, cy), (a, b), ang = cv2.minAreaRect(pts.astype(np.float32))
        corners = cv2.boxPoints(((cx, cy), (a, b), ang))
        wid, lng = min(a, b) * mpp, max(a, b) * mpp
        area = sum(shoelace(p) for p in polys) * mpp * mpp
        zc = mpp * f  # camera to road distance implied by the scale (road about normal to the view)
    eff = mode
    if eff == "ground_plane" and scale.get("horizon_src") == "fallback":
        scale_unc = SCALE_UNC["ground_fallback"]
    else:
        scale_unc = SCALE_UNC[eff]

    # ---------- depth from relative inverse depth: residual below a plane fitted to the road ring
    mask = np.zeros((h, w), np.uint8)
    cv2.fillPoly(mask, [p.astype(np.int32) for p in polys], 1)
    if mask.sum() < 20:
        x1, y1, x2, y2 = (int(v) for v in (row["x1"], row["y1"], row["x2"], row["y2"]))
        mask[y1:y2, x1:x2] = 1
    r = max(5, int(0.5 * math.sqrt(max(mask.sum(), 1))))
    m_in = cv2.dilate(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)))
    m_out = cv2.dilate(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1)))
    ring = (m_out > 0) & (m_in == 0)
    ys_r, xs_r = np.nonzero(ring)
    ys_i, xs_i = np.nonzero(mask)
    reliable, reason, rel_in = True, "", np.zeros(len(xs_i))
    if len(xs_r) < 40:
        reliable, reason = False, "too little road around the hole"
        dep = np.zeros(len(xs_i))
    else:
        step = max(1, len(xs_r) // 6000)
        xs_r, ys_r = xs_r[::step], ys_r[::step]
        vr = D[ys_r, xs_r].astype(np.float64)
        coef, kept = _plane_fit(xs_r.astype(np.float64), ys_r.astype(np.float64), vr)
        plane_r = coef[0] + coef[1] * xs_r + coef[2] * ys_r
        plane_in = coef[0] + coef[1] * xs_i + coef[2] * ys_i
        d_in = D[ys_i, xs_i].astype(np.float64)
        pm = max(float(np.median(plane_r)), 1e-6)
        sigma = float(np.std((vr - plane_r)[kept])) / pm  # relative noise of the road ring
        rel_in = np.clip((plane_in - d_in) / np.maximum(plane_in, 1e-6), 0, 0.9)  # 1 - Z/Z' = relative deficit
        # a floor at inverse depth d below the plane: D_plane / D = Z' / Z  ->  depth = Zc * (D_plane / D - 1)
        ratio = np.maximum(plane_in, 1e-6) / np.maximum(d_in, 1e-6)
        ratio = np.clip(ratio, 1.0, 3.0)
        if eff == "ground_plane":
            dep = H * (ratio - 1.0)  # point on the same ray, below the road: depth below plane = H (Z'/Z - 1)
        else:
            dep = zc * (ratio - 1.0)
        mean_rel = float(rel_in.mean())
        p90 = float(np.percentile(rel_in, 90))
        if os.environ.get("MEASURE_DEBUG"):
            print("DBG", idx, "sigma", round(sigma, 4), "mean_rel", round(mean_rel, 4), "p90", round(p90, 4),
                  "wid", round(wid, 2), "depth_p95_cm", round(float(np.percentile(np.clip(dep, 0, None), 95)) * 100, 1))
        if plane_in.mean() <= 0 or pm <= 0:
            reliable, reason = False, "the road plane fit failed"
        elif p90 < 3.0 * sigma or mean_rel < 1.0 * sigma:
            reliable, reason = False, "the hole floor is not separable from road noise in the depth model"
        elif p90 < 0.02:
            reliable, reason = False, "the depth model sees almost no drop inside the outline"
    dep = np.clip(dep, 0, None)

    ratio_cap = DEPTH_WIDTH_CAP
    cap = min(0.30, ratio_cap * wid)
    lo_r, hi_r = PRIOR_RATIO
    dunc = DEPTH_UNC[eff] if eff != "ground_plane" or scale.get("horizon_src") != "fallback" else DEPTH_UNC["closeup"]
    if reliable:
        raw_max = float(np.percentile(dep, 95))
        raw_mean = float(dep.mean())
        if raw_max > cap:
            notes.append(f"Raw depth {raw_max * 100:.0f} cm exceeded {ratio_cap:.2f} x width and was limited to "
                         f"{cap * 100:.0f} cm.")
            k = cap / raw_max
            raw_max, raw_mean = cap, raw_mean * k
        if raw_max < 0.01:
            notes.append("Measured drop is under 1 cm, reported as 1 cm.")
        dmax = float(np.clip(raw_max * 100, 1, 30))
        dmean = float(np.clip(raw_mean * 100, 1, dmax))
        d_lo, d_hi = dmax * (1 - dunc / 100), dmax * (1 + dunc / 100)
        m_lo, m_hi = dmean * (1 - dunc / 100), dmean * (1 + dunc / 100)
    else:
        notes.append(f"Depth not reliable: {reason}. Showing an estimate from typical pothole proportions and the "
                     f"photo's dark contrast, range {lo_r * 100:.0f} to {hi_r * 100:.0f} percent of width.")
        frac = lo_r + (hi_r - lo_r) * 0.0 + 0.10 * float(np.clip(row.get("depth_index", 0.4), 0, 1))
        frac = float(np.clip(frac, lo_r, hi_r))
        dmax = float(np.clip(frac * wid * 100, 1, 30))
        dmean = 0.6 * dmax
        d_lo, d_hi = max(1.0, lo_r * wid * 100), min(30.0, hi_r * wid * 100)
        d_hi = max(d_hi, d_lo)
        m_lo, m_hi = d_lo * 0.6, d_hi * 0.6
    if row.get("water"):
        notes.append("Standing water detected: the water surface reflects, so depth is underestimated.")

    def v_l(depth_cm):  # litres
        return depth_cm / 100.0 * area * 1000.0

    r1 = lambda v: None if v is None else round(float(v), 1)
    vol = v_l(dmean)
    res = {
        "index": idx, "confidence": round(float(row.get("confidence", 1.0)), 3),
        "box": [round(float(row[k]), 1) for k in ("x1", "y1", "x2", "y2")],
        "width_cm": round(wid * 100, 1), "length_cm": round(lng * 100, 1), "area_m2": round(area, 3),
        "depth_reliable": bool(reliable), "size_reliable": bool(size_ok),
        "depth_source": "depth model residual" if reliable else "typical proportions (estimate)",
        "depth_max_cm": r1(dmax), "depth_mean_cm": r1(dmean),
        "depth_max_range_cm": [r1(d_lo), r1(d_hi)], "depth_mean_range_cm": [r1(m_lo), r1(m_hi)],
        "depth_width_ratio": round(dmax / (wid * 100), 3),
        "width_range_cm": [r1(wid * 100 * (1 - scale_unc / 100)), r1(wid * 100 * (1 + scale_unc / 100))],
        "length_range_cm": [r1(lng * 100 * (1 - scale_unc / 100)), r1(lng * 100 * (1 + scale_unc / 100))],
        "volume_litres": r1(vol), "volume_range_litres": [r1(v_l(m_lo)), r1(v_l(m_hi))],
        "cold_mix_kg": r1(vol / 1000.0 * ASPHALT_KG_M3 * COMPACTION),
        "cold_mix_range_kg": [r1(v_l(m_lo) / 1000.0 * ASPHALT_KG_M3 * COMPACTION),
                              r1(v_l(m_hi) / 1000.0 * ASPHALT_KG_M3 * COMPACTION)],
        "scale_mode": eff, "scale_mode_label": MODE_WORDS[eff],
        "uncertainty_pct": scale_unc, "depth_uncertainty_pct": dunc,
        "depth_confidence": DEPTH_CONF[eff] if reliable else "estimate only",
        "distance_m": round(zc, 2), "water": bool(row.get("water")), "outline": src, "notes": notes,
    }
    viz = {"polys": polys, "corners": corners, "mask": mask, "dep": rel_in, "idx": (ys_i, xs_i)}
    return res, viz


def _scale_for(img, D, reference, ref_box, camera, rows):
    h, w = img.shape[:2]
    f = focal_px(w, h)
    y_dep, r2 = horizon_from_depth(D) if D is not None else (None, 0.0)
    y_hough, hough_found = find_horizon(img)
    landscape = w >= h
    if y_dep is not None and r2 >= 0.9:
        yh, src = y_dep, "depth"
    elif hough_found:
        yh, src = y_hough, "hough"
    else:
        yh, src = 0.4 * h, "fallback"
    cam = camera if camera in ("phone", "dashcam") else ("dashcam" if landscape and src != "fallback" and yh > 0.25 * h
                                                         else "phone")
    H = H_DASH if cam == "dashcam" else H_PHONE
    sc = {"f": f, "yh": yh, "horizon_src": src, "horizon_found": src != "fallback", "camera": cam, "H": H,
          "r2": round(r2, 3), "hough_y": round(y_hough, 1) if hough_found else None}
    if reference and ref_box:
        rx1, ry1, rx2, ry2 = ref_box
        px = max(abs(rx2 - rx1), abs(ry2 - ry1))
        if px >= 4:
            sc.update(mode="reference", mpp=(reference["length_cm"] / 100.0) / px)
            return sc
    big = max(((r["x2"] - r["x1"]) * (r["y2"] - r["y1"]) / float(w * h) for r in rows), default=0)
    if big > 0.25 and src != "depth":
        sc.update(mode="closeup", mpp=CLOSEUP_FRAME_M / w)
    elif src == "fallback" and big > 0.12:
        sc.update(mode="closeup", mpp=CLOSEUP_FRAME_M / w)
    else:
        sc.update(mode="ground_plane", mpp=None)
    return sc


def _annotate(img, D, results, vizs, out_path):
    out = img.copy()
    h, w = out.shape[:2]
    th = max(1, int(round(max(h, w) / 600)))
    fs = max(0.5, max(h, w) / 1400)
    for res, v in zip(results, vizs):
        cv2.polylines(out, [p.astype(np.int32) for p in v["polys"]], True, (60, 220, 60), th + 1)
        c = np.asarray(v["corners"], np.float64)
        cv2.polylines(out, [c.astype(np.int32)], True, (0, 210, 255), th + 1)
        sides = [(c[i], c[(i + 1) % 4]) for i in range(4)]
        lens = [np.linalg.norm(b - a) for a, b in sides]
        # label one short side as width and one long side as length
        si = int(np.argmin(lens[:2]))
        for k, (txt) in ((si, f'W {res["width_cm"]:.0f} cm'), (1 - si, f'L {res["length_cm"]:.0f} cm')):
            a, b = sides[k]
            m = ((a + b) / 2).astype(int)
            _label(out, txt, (int(m[0]), int(m[1])), fs, th)
        x1, y1 = int(res["box"][0]), int(res["box"][1])
        dtxt = (f'depth {res["depth_max_cm"]:.0f} cm max' if res["depth_reliable"]
                else f'depth ~{res["depth_max_range_cm"][0]:.0f} to {res["depth_max_range_cm"][1]:.0f} cm (est.)')
        _label(out, f'#{res["index"] + 1} {dtxt}', (x1, max(20, y1 - 8)), fs, th)
    # depth inset per pothole (up to 3), stacked on the left
    iw = max(120, w // 5)
    y0 = 8
    for res, v in list(zip(results, vizs))[:3]:
        x1, y1, x2, y2 = (int(t) for t in res["box"])
        pad = int(0.25 * max(x2 - x1, y2 - y1))
        X1, Y1, X2, Y2 = max(0, x1 - pad), max(0, y1 - pad), min(w, x2 + pad), min(h, y2 + pad)
        if X2 - X1 < 4 or Y2 - Y1 < 4:
            continue
        hm = np.zeros((h, w), np.float32)
        ys, xs = v["idx"]
        hm[ys, xs] = v["dep"]
        crop = hm[Y1:Y2, X1:X2]
        mx = max(float(crop.max()), 0.05)
        col = cv2.applyColorMap((np.clip(crop / mx, 0, 1) * 255).astype(np.uint8), cv2.COLORMAP_INFERNO)
        ih = int(iw * (Y2 - Y1) / (X2 - X1))
        ih = min(ih, h // 3)
        col = cv2.resize(col, (iw, ih))
        if y0 + ih + 4 > h:
            break
        out[y0:y0 + ih, 8:8 + iw] = col
        cv2.rectangle(out, (8, y0), (8 + iw, y0 + ih), (255, 255, 255), 1)
        _label(out, f'#{res["index"] + 1} depth' + ('' if res["depth_reliable"] else ' (unreliable)'),
               (12, y0 + int(22 * fs)), fs * 0.8, th)
        y0 += ih + 8
    cv2.imwrite(str(out_path), out, [cv2.IMWRITE_JPEG_QUALITY, 88])


def _label(img, txt, org, fs, th):
    (tw, tht), bl = cv2.getTextSize(txt, cv2.FONT_HERSHEY_SIMPLEX, fs, th)
    x, y = org
    x = int(min(max(0, x - tw // 2), img.shape[1] - tw - 2))
    y = int(min(max(tht + 2, y), img.shape[0] - 2))
    cv2.rectangle(img, (x - 2, y - tht - 3), (x + tw + 2, y + bl), (20, 20, 20), -1)
    cv2.putText(img, txt, (x, y), cv2.FONT_HERSHEY_SIMPLEX, fs, (255, 255, 255), th, cv2.LINE_AA)


def _method(sc, depth_ms):
    d = _depth
    return {
        "detection": "Detector boxes plus the traced damaged outline (OpenCV segmentation) for each pothole.",
        "scale": {
            "reference": "Reference object: real length divided by the long side of its box in pixels, about 10 percent.",
            "ground_plane": "Camera height and pitched-camera perspective with the horizon from the depth model, each "
                            "outline point mapped onto the road plane, about 30 percent.",
            "closeup": "Close-up or no usable horizon: about 2 m of road across the frame width, about 60 percent.",
        },
        "size": "minAreaRect of the outline on the road plane, width = shorter side, length = longer side, "
                "area = outline area on the road plane.",
        "depth": f"{DEPTH_MODEL_ID} relative inverse depth, robust plane fit to a road ring around the outline, "
                 "residual below the plane converted to metres from the camera geometry and capped at 0.35 x width. If the "
                 "residual is not separable from road noise the depth is reported as not reliable with a range.",
        "volume": "mean depth x area, cold mix = volume x 2300 kg/m3 x 1.1 compaction.",
        "camera": sc["camera"], "camera_height_m": sc["H"], "fov_deg": FOV_DEG, "focal_px": round(sc["f"], 1),
        "horizon_y": round(sc["yh"], 1), "horizon_source": {
            "depth": "zero of the depth model's road profile", "hough": "road edge vanishing point",
            "fallback": "fallback at 40 percent of the image height"}[sc["horizon_src"]],
        "horizon_profile_r2": sc["r2"], "horizon_hough_y": sc["hough_y"],
        "depth_model": DEPTH_MODEL_ID, "depth_device": d["device"], "depth_ms": depth_ms,
    }


def measure_image(img, reference=None, ref_box=None, camera="auto", box=None, rows=None, tag="m"):
    t0 = time.time()
    h, w = img.shape[:2]
    if rows is None:
        if box:
            rows = [detector.make_row(img, "pothole", *box, 1.0)]
        else:
            rows = [r for r in detector.detect_image(img)[0] if r["class_name"] == "pothole"]
    td = time.time()
    D = depth_map(img) if rows else None
    depth_ms = int((time.time() - td) * 1000) if rows else 0
    sc = _scale_for(img, D, reference, ref_box, camera, rows)
    common = []
    if sc["mode"] == "reference":
        common.append(f'Scale from the {REFERENCE_WORDS.get(reference.get("type"), "reference")} '
                      f'({reference["length_cm"]:g} cm).')
    elif sc["mode"] == "ground_plane" and sc["horizon_src"] == "fallback":
        common.append("Horizon not found, assumed at 40 percent of the image height, so size is a rough guess.")
    results, vizs = [], []
    if rows:
        for i, r in enumerate(rows):
            res, v = _measure_one(img, D, r, i, sc, common)
            results.append(res)
            vizs.append(v)
        out_path = config.ANNOTATED / f"measure_{tag}.jpg"
        _annotate(img, D, results, vizs, out_path)
        ann = f"/media/annotated/{out_path.name}"
    else:
        ann = None
    return {"potholes": results, "annotated_url": ann, "image_size": [w, h], "method": _method(sc, depth_ms),
            "ms": int((time.time() - t0) * 1000)}


def _cache_get(k):
    v = _cache.get(k)
    if v is not None:
        _cache.move_to_end(k)
    return v


def _cache_put(k, v):
    _cache[k] = v
    while len(_cache) > CACHE_MAX:
        _cache.popitem(last=False)


def _parse_box(s: Optional[str]):
    if not s:
        return None
    try:
        v = [float(t) for t in s.replace(" ", "").split(",")]
    except ValueError:
        raise HTTPException(400, "box must be x1,y1,x2,y2")
    if len(v) != 4:
        raise HTTPException(400, "box must be x1,y1,x2,y2")
    x1, y1, x2, y2 = v
    return [min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)]


def _read_detection_frame(det, insp):
    p = Path(insp.stored_path or "")
    if not p.exists():
        return None
    if insp.media_type == "image":
        return cv2.imdecode(np.fromfile(str(p), dtype=np.uint8), cv2.IMREAD_COLOR)
    cap = cv2.VideoCapture(str(p))
    try:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(det.frame_index or 0))
        ok, fr = cap.read()
        return fr if ok else None
    finally:
        cap.release()


def register(app):
    @app.post("/api/measure")
    def measure(file: UploadFile = File(...), reference_type: Optional[str] = Form(None),
                reference_length_cm: Optional[float] = Form(None), ref_box: Optional[str] = Form(None),
                camera: str = Form("auto"), box: Optional[str] = Form(None)):
        data = file.file.read()
        img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            raise HTTPException(400, "Could not decode image")
        reference = None
        rb = _parse_box(ref_box)
        if reference_type:
            rt = reference_type.strip().lower()
            if rt == "custom":
                if not reference_length_cm or reference_length_cm <= 0:
                    raise HTTPException(400, "custom reference needs reference_length_cm")
                reference = {"type": "custom", "length_cm": float(reference_length_cm)}
            elif rt in REFERENCES_CM:
                reference = {"type": rt, "length_cm": REFERENCES_CM[rt]}
            else:
                raise HTTPException(400, f"reference_type must be one of {sorted(REFERENCES_CM) + ['custom']}")
            if rb is None:
                raise HTTPException(400, "ref_box is required with a reference object")
        bx = _parse_box(box)
        key = hashlib.sha1(data).hexdigest()
        ck = f"{key}|{reference}|{rb}|{camera}|{bx}"
        hit = _cache_get(ck)
        if hit is not None:
            return dict(hit, cached=True)
        res = measure_image(img, reference, rb, camera, box=bx, tag=hashlib.sha1(ck.encode()).hexdigest()[:16])
        res["reference"] = reference
        _cache_put(ck, res)
        return res

    @app.post("/api/measure/warmup")
    def warmup():
        """Load the small depth model in the background so the first measurement is fast."""
        if _depth["model"] is None:
            def _go():
                try:
                    with _lock:
                        _load_depth()
                except Exception:
                    pass
            threading.Thread(target=_go, daemon=True).start()
            return {"status": "loading"}
        return {"status": "ready", "device": _depth["device"]}

    @app.get("/api/measure/defect/{defect_id}")
    def measure_defect(defect_id: int, camera: str = "auto"):
        s = SessionLocal()
        try:
            dets = (s.query(Detection).filter(Detection.defect_id == defect_id)
                    .order_by(Detection.created_at.desc(), Detection.id.desc()).all())
            if not dets:
                raise HTTPException(404, "No detections for this defect")
            for det in dets:
                insp = s.get(Inspection, det.inspection_id)
                if insp is None:
                    continue
                img = _read_detection_frame(det, insp)
                if img is None:
                    continue
                ck = f"defect|{det.id}|{camera}"
                hit = _cache_get(ck)
                if hit is not None:
                    return dict(hit, cached=True)
                box = [det.x1, det.y1, det.x2, det.y2]
                row = detector.make_row(img, "pothole", *box, det.confidence or 1.0)
                res = measure_image(img, None, None, camera, rows=[row], tag=f"defect_{det.id}")
                res.update(defect_id=defect_id, detection_id=det.id, inspection_id=insp.id,
                           class_name=det.corrected_class or det.class_name)
                _cache_put(ck, res)
                return res
            raise HTTPException(404, "The source image for this defect is not available")
        finally:
            s.close()

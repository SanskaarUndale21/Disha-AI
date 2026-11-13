"""Pothole size and depth measurement from a single photo.

Method
1. Detection. detector.detect_image gives each pothole a box and a traced damaged outline (polygon, OpenCV
   segmentation in severity.py). Every pothole row is measured. An explicit box can also be passed.
2. Scale (metres per pixel). The best available source is used and reported with its uncertainty:
   a. Reference object (A4 sheet, credit card, 500 ml bottle, shoe/foot or a custom length) marked with a box:
      m/px = real length / long side of the box in pixels. About plus or minus 10 percent.
   b. Ground-plane geometry for dashcam and phone-at-chest shots: camera height 1.2 m (phone) or 1.4 m
      (dashcam: landscape image with a visible horizon), horizontal field of view about 66 degrees across the long
      side of the image, so f = (long side / 2) / tan(33 deg). The horizon row y_h is the vanishing point of road
      edges and lane lines (Hough lines, median of pairwise intersections), fallback 40 percent of the height.
      A ground point at row y lies at distance Z = H * f / (y - y_h) and lateral offset X = (x - cx) * Z / f.
      Every polygon vertex is mapped onto the road plane this way (inverse perspective), which is the same as
      summing per-row scaled strips, so the far edge of a hole is not under-measured. About plus or minus 30 percent.
   c. Close-up top-down photos (pothole box covers more than 25 percent of the frame and no horizon found):
      the frame width is assumed to show about 1.2 m of road. About plus or minus 40 percent.
3. Width, length, area. cv2.minAreaRect of the outline (in road-plane metres for ground-plane mode, else in
   pixels times m/px): width = shorter side, length = longer side. Area = shoelace area of the outline on the
   road plane. Fallback outline: an ellipse inside the box.
4. Depth. Depth Anything V2 Small (Apache-2.0, depth-anything/Depth-Anything-V2-Small-hf) runs on the image with
   the long side resized to 518. It returns relative inverse depth D, affine in 1/Z. A plane D = p0 + p1 x + p2 y
   is fitted by least squares with outlier rejection to a ring of road just outside the outline. Inside the hole
   the floor lies below that plane. On a flat road 1/Z is linear in the row, so the fitted plane evaluated at the
   horizon row gives the shift b of the model output (1/Z = 0 at the horizon) and the row gradient p2 gives its
   scale (geometric change of 1/Z per row is 1 / (H f)). A hole floor seen through pixel (x, y) at depth d below
   the road satisfies (D_plane - b) / (D - b) = (H + d) / H, so d = H * ((D_plane - b) / (D - b) - 1).
   In close-up and reference mode the camera distance is Zc = m/px * f and the shift b is taken as 0, so
   d = Zc * (D_plane / D - 1), then capped at 0.6 x the hole width and 30 cm. Max depth = 95th percentile of d
   inside the outline, mean depth = mean of d inside the outline, both clamped to 1 to 30 cm. Confidence is high
   with a reference object, medium for ground-plane and low for close-ups. Standing water reflects, so depth is
   underestimated when water is detected.
5. Volume = mean depth x area (litres = m3 x 1000). Cold mix kg = volume m3 x 2300 kg/m3 x 1.1 compaction.
6. Annotated image: outline, minimum-area rectangle with width and length labels in cm and a small depth inset.
"""
import hashlib
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
CLOSEUP_FRAME_M = 1.2
REFERENCES_CM = {"a4": 29.7, "credit_card": 8.56, "bottle_500ml": 21.0, "foot": 27.0}
REFERENCE_WORDS = {"a4": "A4 sheet", "credit_card": "credit card", "bottle_500ml": "500 ml bottle",
                   "foot": "shoe or foot", "custom": "custom reference"}
MODE_WORDS = {"reference": "Measured against the reference object you marked",
              "ground_plane": "Estimated from camera height and perspective",
              "closeup": "Close-up photo: assumes about 1.2 m of road across the frame",
              "box": "Box supplied by the request"}
SCALE_UNC = {"reference": 10, "ground_plane": 30, "closeup": 40}
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
    try:
        m = AutoModelForDepthEstimation.from_pretrained(DEPTH_MODEL_ID, dtype=dt)
    except TypeError:  # older transformers
        m = AutoModelForDepthEstimation.from_pretrained(DEPTH_MODEL_ID, torch_dtype=dt)
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


def to_ground(pts, cx, yh, f, H, h):
    """Image points -> road-plane metres (X lateral, Z forward)."""
    p = np.asarray(pts, np.float64)
    dy = np.maximum(p[:, 1] - yh, 0.03 * h)
    Z = H * f / dy
    X = (p[:, 0] - cx) * Z / f
    return np.stack([X, Z], 1)


def from_ground(g, cx, yh, f, H):
    g = np.asarray(g, np.float64)
    Z = np.maximum(g[:, 1], 1e-3)
    return np.stack([cx + g[:, 0] * f / Z, yh + H * f / Z], 1)


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
    return coef


# ---------------------------------------------------------------- core
def _measure_one(img, D, row, idx, scale, notes_common):
    h, w = img.shape[:2]
    polys, src = outline(row, w, h)
    pts = np.vstack(polys)
    mode = scale["mode"]
    notes = list(notes_common)
    if src != "traced outline":
        notes.append("Outline not traced, an ellipse inside the box was used.")

    def ground_measure():
        g_polys = [to_ground(p, w / 2, scale["yh"], scale["f"], scale["H"], h) for p in polys]
        gp = np.vstack(g_polys).astype(np.float32)
        (gcx, gcy), (a, b), ang = cv2.minAreaRect(gp)
        corners_g = cv2.boxPoints(((gcx, gcy), (a, b), ang))
        corners_i = from_ground(corners_g, w / 2, scale["yh"], scale["f"], scale["H"])
        area = sum(shoelace(gpo) for gpo in g_polys)
        return min(a, b), max(a, b), area, corners_i, corners_g

    if mode == "ground_plane":
        wid, lng, area, corners, corners_g = ground_measure()
        dist = float(np.median(to_ground(pts, w / 2, scale["yh"], scale["f"], scale["H"], h)[:, 1]))
        if not (0.04 <= wid and lng <= 3.0) or row["y1"] - scale["yh"] < 0.02 * h:
            notes.append("Perspective geometry gave an implausible size here, used the close-up assumption.")
            mode = "closeup_fallback"
    if mode != "ground_plane":
        mpp = scale["mpp"] if scale["mode"] in ("reference", "closeup") else CLOSEUP_FRAME_M / w
        (cx, cy), (a, b), ang = cv2.minAreaRect(pts.astype(np.float32))
        corners = cv2.boxPoints(((cx, cy), (a, b), ang))
        wid, lng = min(a, b) * mpp, max(a, b) * mpp
        area = sum(shoelace(p) for p in polys) * mpp * mpp
        dist = mpp * scale["f"]
    eff_mode = "closeup" if mode == "closeup_fallback" else mode

    # ---------- depth from the relative inverse depth map
    mask = np.zeros((h, w), np.uint8)
    cv2.fillPoly(mask, [p.astype(np.int32) for p in polys], 1)
    if mask.sum() < 20:
        x1, y1, x2, y2 = (int(v) for v in (row["x1"], row["y1"], row["x2"], row["y2"]))
        mask[y1:y2, x1:x2] = 1
    r = max(4, int(0.35 * math.sqrt(max(mask.sum(), 1))))
    m_in = cv2.dilate(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
    m_out = cv2.dilate(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1)))
    ring = (m_out > 0) & (m_in == 0)
    ys_r, xs_r = np.nonzero(ring)
    ys_i, xs_i = np.nonzero(mask)
    step = max(1, len(xs_r) // 6000)
    xs_r, ys_r = xs_r[::step], ys_r[::step]
    coef = _plane_fit(xs_r.astype(np.float64), ys_r.astype(np.float64), D[ys_r, xs_r].astype(np.float64))
    plane_in = coef[0] + coef[1] * xs_i + coef[2] * ys_i
    d_in = D[ys_i, xs_i].astype(np.float64)
    if eff_mode == "ground_plane":
        b = coef[0] + coef[1] * xs_i + coef[2] * scale["yh"]  # plane value at the horizon row: 1/Z = 0 there
        num, den = plane_in - b, d_in - b
        ok = (num > 0) & (den > 0)
        if coef[2] <= 0 or ok.mean() < 0.5:
            notes.append("Depth model output did not follow the road plane well, depth is a rough guess.")
            ok = den > 0
        dep = np.where(ok, scale["H"] * (num / np.maximum(den, 1e-6) - 1.0), 0.0)
    else:
        dep = dist * (plane_in / np.maximum(d_in, 1e-6) - 1.0)
    dep = np.clip(dep, 0, None)
    cap = min(0.30, 0.6 * wid)
    raw_max = float(np.percentile(dep, 95)) if dep.size else 0.0
    raw_mean = float(dep.mean()) if dep.size else 0.0
    if raw_max > cap:
        notes.append(f"Raw depth {raw_max * 100:.0f} cm exceeded the sanity cap and was limited to {cap * 100:.0f} cm.")
        k = cap / raw_max
        raw_max, raw_mean = cap, raw_mean * k
    dmax = float(np.clip(raw_max * 100, 1, 30))
    dmean = float(np.clip(raw_mean * 100, 1, dmax))
    if row.get("water"):
        notes.append("Standing water detected: the water surface reflects, so depth is underestimated.")

    unc = SCALE_UNC[eff_mode]
    dunc = DEPTH_UNC[eff_mode]
    vol_m3 = (dmean / 100.0) * area
    rng = lambda v, p: [round(v * (1 - p / 100), 1), round(v * (1 + p / 100), 1)]
    res = {
        "index": idx, "confidence": round(float(row.get("confidence", 1.0)), 3),
        "box": [round(float(row[k]), 1) for k in ("x1", "y1", "x2", "y2")],
        "width_cm": round(wid * 100, 1), "length_cm": round(lng * 100, 1), "area_m2": round(area, 3),
        "depth_max_cm": round(dmax, 1), "depth_mean_cm": round(dmean, 1),
        "depth_max_range_cm": rng(dmax, dunc), "depth_mean_range_cm": rng(dmean, dunc),
        "width_range_cm": rng(wid * 100, unc), "length_range_cm": rng(lng * 100, unc),
        "volume_litres": round(vol_m3 * 1000, 1), "cold_mix_kg": round(vol_m3 * ASPHALT_KG_M3 * COMPACTION, 1),
        "scale_mode": eff_mode, "scale_mode_label": MODE_WORDS[eff_mode],
        "uncertainty_pct": unc, "depth_uncertainty_pct": dunc, "depth_confidence": DEPTH_CONF[eff_mode],
        "distance_m": round(dist, 2), "water": bool(row.get("water")), "outline": src, "notes": notes,
    }
    viz = {"polys": polys, "corners": corners, "mask": mask, "dep": dep, "idx": (ys_i, xs_i)}
    return res, viz


def _scale_for(img, reference, ref_box, camera, rows):
    h, w = img.shape[:2]
    f = focal_px(w, h)
    yh, found = find_horizon(img)
    landscape = w >= h
    cam = camera if camera in ("phone", "dashcam") else ("dashcam" if landscape and found else "phone")
    H = H_DASH if cam == "dashcam" else H_PHONE
    sc = {"f": f, "yh": yh, "horizon_found": found, "camera": cam, "H": H}
    if reference and ref_box:
        rx1, ry1, rx2, ry2 = ref_box
        px = max(abs(rx2 - rx1), abs(ry2 - ry1))
        if px >= 4:
            sc.update(mode="reference", mpp=(reference["length_cm"] / 100.0) / px)
            return sc
    big = max(((r["x2"] - r["x1"]) * (r["y2"] - r["y1"]) / float(w * h) for r in rows), default=0)
    if big > 0.25 and not found:
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
        _label(out, f'#{res["index"] + 1} depth {res["depth_max_cm"]:.0f} cm max', (x1, max(20, y1 - 8)), fs, th)
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
        mx = max(float(crop.max()), 1e-6)
        col = cv2.applyColorMap((np.clip(crop / mx, 0, 1) * 255).astype(np.uint8), cv2.COLORMAP_INFERNO)
        ih = int(iw * (Y2 - Y1) / (X2 - X1))
        ih = min(ih, h // 3)
        col = cv2.resize(col, (iw, ih))
        if y0 + ih + 4 > h:
            break
        out[y0:y0 + ih, 8:8 + iw] = col
        cv2.rectangle(out, (8, y0), (8 + iw, y0 + ih), (255, 255, 255), 1)
        _label(out, f'#{res["index"] + 1} depth', (12, y0 + int(22 * fs)), fs * 0.8, th)
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
            "ground_plane": "Camera height and perspective: Z = H f / (y - y_h), X = (x - cx) Z / f, each outline "
                            "point mapped onto the road plane, about 30 percent.",
            "closeup": "Close-up: about 1.2 m of road across the frame width, about 40 percent.",
        },
        "size": "minAreaRect of the outline on the road plane, width = shorter side, length = longer side, "
                "area = outline area on the road plane.",
        "depth": f"{DEPTH_MODEL_ID} relative inverse depth, robust plane fit to a road ring around the outline, "
                 "residual below the plane converted to metres from the camera geometry, clamped 1 to 30 cm.",
        "volume": "mean depth x area, cold mix = volume x 2300 kg/m3 x 1.1 compaction.",
        "camera": sc["camera"], "camera_height_m": sc["H"], "fov_deg": FOV_DEG, "focal_px": round(sc["f"], 1),
        "horizon_y": round(sc["yh"], 1), "horizon_source": "road edge vanishing point" if sc["horizon_found"]
        else "fallback at 40 percent of the image height",
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
    sc = _scale_for(img, reference, ref_box, camera, rows)
    common = []
    if sc["mode"] == "reference":
        common.append(f'Scale from the {REFERENCE_WORDS.get(reference.get("type"), "reference")} '
                      f'({reference["length_cm"]:g} cm).')
    elif sc["mode"] == "ground_plane" and not sc["horizon_found"]:
        common.append("Horizon not visible, assumed at 40 percent of the image height.")
    results, vizs, depth_ms = [], [], 0
    if rows:
        td = time.time()
        D = depth_map(img)
        depth_ms = int((time.time() - td) * 1000)
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

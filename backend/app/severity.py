"""OpenCV damage analysis inside a detection box: segmentation mask, physical-size proxy, depth proxy, severity.

Why: bounding-box area alone says Low for every far-away pothole and High for every close-up photo. Here:
  1. The damaged region is segmented inside the box (LAB lightness + local contrast + edges, Otsu, morphology),
     giving the real damaged pixel area and an outline polygon to draw.
  2. Size is perspective-corrected for road-level cameras: objects higher in the frame (closer to the horizon)
     are farther away, so their pixel size is scaled up by a ground-plane factor.
  3. Depth proxy: contrast between the damaged region and the surrounding asphalt ring (dark shadowed or
     water-filled holes differ strongly from the road surface), plus edge density (broken, rough edges).
  4. severity_score = weighted mix, thresholds Low < 0.33 <= Medium < 0.6 <= High.
"""
import cv2
import numpy as np

HORIZON = 0.38  # typical dashcam horizon height as a fraction of image height


def perspective_factor(y2, h, top_down=False):
    """>1 for objects far up the frame (they are farther away, so their true size is larger than pixels say)."""
    if top_down:
        return 1.0
    v = (y2 / h - HORIZON) / (1 - HORIZON)
    return float(1.0 / max(0.4, min(1.0, v)))


MAX_SIDE = 112  # analysis resolution (keeps it ~2-4 ms per box)


def analyze(frame, cls, x1, y1, x2, y2, conf=1.0):
    h, w = frame.shape[:2]
    x1, y1 = int(max(0, x1)), int(max(0, y1))
    x2, y2 = int(min(w, x2)), int(min(h, y2))
    bw, bh = max(1, x2 - x1), max(1, y2 - y1)
    roi = frame[y1:y2, x1:x2]
    if roi.size < 48 or bw < 6 or bh < 6:
        return _result(cls, 0.5, 0, 0, 0.5 * bw * bh, [], conf, 1.0, w, h, bw, bh)
    sc = min(1.0, MAX_SIDE / max(bw, bh))
    small = cv2.resize(roi, (max(4, int(bw * sc)), max(4, int(bh * sc))), interpolation=cv2.INTER_AREA)
    sh, sw = small.shape[:2]
    lab = cv2.cvtColor(cv2.GaussianBlur(small, (3, 3), 0), cv2.COLOR_BGR2LAB).astype(np.float32)

    # road reference = the band just inside the box border (a tight box around damage is framed by intact road)
    band = max(2, int(0.1 * min(sh, sw)))
    bm = np.zeros((sh, sw), bool)
    bm[:band, :] = bm[-band:, :] = True
    bm[:, :band] = bm[:, -band:] = True
    ref = np.median(lab[bm], axis=0)
    color_d = np.linalg.norm((lab - ref) * np.array([1.0, 1.6, 1.6], np.float32), axis=2)
    L = lab[:, :, 0]
    mu = cv2.blur(L, (5, 5))
    texture = np.sqrt(np.clip(cv2.blur(L * L, (5, 5)) - mu * mu, 0, None))
    tex_ref = float(np.median(texture[bm]))
    score = color_d / (np.percentile(color_d, 95) + 1e-6) + 0.5 * np.clip(texture - tex_ref, 0, None) / (
        np.percentile(texture, 95) + 1e-6)
    s8 = np.clip(score / (score.max() + 1e-6) * 255, 0, 255).astype(np.uint8)
    _, m = cv2.threshold(s8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    k = 3 if min(sh, sw) < 40 else 5
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k + 2, k + 2)))

    n, lbl, stats, cent = cv2.connectedComponentsWithStats(m)
    mask = np.zeros_like(m)
    if n > 1:
        # the detector centres the damage: rank components by how much of the central ellipse they cover
        core = np.zeros_like(m)
        cv2.ellipse(core, (sw // 2, sh // 2), (max(1, int(sw * 0.3)), max(1, int(sh * 0.3))), 0, 0, 360, 1, -1)
        cover = np.bincount(lbl[core > 0].ravel(), minlength=n)
        cand = [(cover[i], i) for i in range(1, n) if stats[i, cv2.CC_STAT_AREA] >= 0.02 * sw * sh and cover[i] > 0]
        cand.sort(reverse=True)
        if cls == "pothole":
            cand = cand[:1]
        for _, i in cand:
            mask[lbl == i] = 255
    fill = float(mask.mean() / 255.0)
    if fill < 0.06 or fill > 0.97:  # segmentation unreliable: ellipse prior inside the box
        mask = np.zeros_like(m)
        cv2.ellipse(mask, (sw // 2, sh // 2), (max(1, int(sw * 0.4)), max(1, int(sh * 0.4))), 0, 0, 360, 255, -1)
        fill = float(mask.mean() / 255.0)

    inside = mask > 0
    contrast = abs(float(L[inside].mean()) - float(ref[0])) / 255.0
    edges = cv2.Canny(small, 60, 160)
    edge_density = float((edges[inside] > 0).mean())
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    poly = []
    for c in sorted(cnts, key=cv2.contourArea, reverse=True)[:3]:
        c = cv2.approxPolyDP(c, 0.015 * cv2.arcLength(c, True), True)
        poly.append([[int(p[0][0] / sc + x1), int(p[0][1] / sc + y1)] for p in c])
    top_down = (bw * bh) / float(w * h) > 0.18
    pf = perspective_factor(y2, h, top_down)
    dmg_px = fill * bw * bh
    # standing water: a smooth (low texture), low-saturation, brighter-than-road region inside the hole
    water = False
    if cls == "pothole" and inside.any():
        hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
        sat = float(hsv[:, :, 1][inside].mean())
        smooth = float(texture[inside].mean()) < 0.6 * (tex_ref + 1e-6) + 2
        water = smooth and sat < 60 and float(L[inside].mean()) > float(ref[0]) + 12
    return _result(cls, fill, contrast, edge_density, dmg_px, poly, conf, pf, w, h, bw, bh, water)


# calibrated on ground-truth pothole boxes (ml/calibrate_severity.py): ~90th percentile of each raw measure
CAL = {"size_ref": {"pothole": 0.20, "alligator_crack": 0.30, "linear": 0.9}, "depth_ref": 0.29, "rough_ref": 0.40,
       "low_max": 0.34, "med_max": 0.62,
       # 4-level scale, cut at the 35th / 70th / 90th percentile of 2,400 ground-truth potholes
       "levels": [(0.315, "Minor"), (0.534, "Moderate"), (0.745, "Severe"), (9.0, "Critical")]}

LEVELS = ["Minor", "Moderate", "Severe", "Critical"]
LEVEL_RANK = {"Minor": 0, "Moderate": 1, "Severe": 2, "Critical": 3, "Low": 0, "Medium": 1, "High": 2}
LEVEL_SCORE = {"Minor": 0.2, "Moderate": 0.42, "Severe": 0.64, "Critical": 0.85, "Low": 0.2, "Medium": 0.5, "High": 0.8}


def level_for(score):
    for cut, name in CAL["levels"]:
        if score < cut:
            return name
    return "Critical"


def _result(cls, fill, contrast, edge_density, dmg_px, poly, conf, pf, w, h, bw, bh, water=False):
    diag = float(np.hypot(w, h))
    if cls in ("pothole", "alligator_crack"):
        # equivalent diameter of the damaged region relative to the image diagonal, perspective corrected
        size = (np.sqrt(max(dmg_px, 1.0)) / diag) * pf
        size_n = float(np.clip(size / CAL["size_ref"][cls], 0, 1))
    else:
        # crack length relative to the image side, perspective corrected
        size = (max(bw, bh) / max(w, h)) * pf
        size_n = float(np.clip(size / CAL["size_ref"]["linear"], 0, 1))
    depth_n = float(np.clip(contrast / CAL["depth_ref"], 0, 1))
    rough_n = float(np.clip(edge_density / CAL["rough_ref"], 0, 1))
    if cls == "pothole":
        score = 0.55 * size_n + 0.30 * depth_n + 0.15 * rough_n
    elif cls == "alligator_crack":
        score = 0.60 * size_n + 0.15 * depth_n + 0.25 * rough_n
    else:
        score = 0.70 * size_n + 0.20 * depth_n + 0.10 * rough_n
    score = float(np.clip(score * (0.85 + 0.15 * float(conf)), 0, 1))
    if water and cls == "pothole":
        score = max(score, 0.55)  # standing water hides the true depth: never rate below Severe-adjacent
    label = level_for(score)
    return {
        "area_ratio": round(dmg_px / float(w * h), 6),
        "damage_fill": round(fill, 3),
        "size_index": round(size_n, 3),
        "depth_index": round(depth_n, 3),
        "roughness_index": round(rough_n, 3),
        "perspective": round(pf, 2),
        "severity": label,
        "severity_score": round(score, 4),
        "polygon": poly,
        "water": bool(water),
        "raw": {"size": round(float(size), 4), "contrast": round(contrast, 4), "edges": round(edge_density, 4)},
    }


METHOD = {
    "segmentation": "Otsu on |L - road L| inside box (+ adaptive dark threshold and Canny edges for cracks), "
                    "morphological open/close, largest contour for potholes",
    "size_index": "sqrt(damaged px)/image diagonal x perspective factor (ground plane, horizon at 38% height); "
                  "crack length = box major axis / image side x perspective",
    "depth_index": "|mean L(damage) - median L(surrounding road ring)| / 0.22",
    "roughness_index": "Canny edge density inside damage / 0.25",
    "score": "pothole 0.55 size + 0.30 depth + 0.15 roughness; alligator 0.60/0.15/0.25; linear cracks 0.70/0.20/0.10",
    "levels": {"Minor": "< 0.315", "Moderate": "0.315 - 0.534", "Severe": "0.534 - 0.745", "Critical": ">= 0.745"},
    "water": "smooth, low-saturation region brighter than the road inside a pothole = standing water (rated at least 0.55)",
    "calibration": "normalisers = 90th percentile and cut points = 40th/80th percentile over 2400 ground-truth pothole boxes (ml/calibrate_severity.py): 35% Minor, 35% Moderate, 20% Severe, 10% Critical",
}

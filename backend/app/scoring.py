"""Severity classification and road-damage risk scoring.

Severity (per detection) uses the defect's physical extent in the frame, normalised per class:
  - potholes / alligator cracking: bbox area as a fraction of the image (area damage)
  - longitudinal / transverse cracks: bbox major-axis length as a fraction of the image side (linear damage)
  then a confidence-weighted continuous score in [0, 1] and Low / Medium / High bands.

Risk score (0..100):
  risk = 100 * (0.45 * severity_score + 0.25 * class_hazard + 0.30 * road_factor)
         + repeat bonus (+4 per extra independent report, max +12)
         + trend bonus (+8 if worsening)
  road_factor = 0.5 * road_type_weight + 0.5 * traffic_weight (unknown = 0.5, never invented)
  bands: >= 70 High, >= 40 Medium, else Low.
"""

CLASS_HAZARD = {
    "pothole": 1.0,
    "alligator_crack": 0.75,
    "transverse_crack": 0.5,
    "longitudinal_crack": 0.4,
    "manhole": 0.8,        # sunken or open covers are a serious two-wheeler hazard
    "debris": 0.6,
    "speed_breaker": 0.35,  # hazardous mainly when unmarked
    "barricade": 0.2,       # marks an active work zone rather than damage
}
ROAD_TYPE_W = {"highway": 1.0, "arterial": 0.8, "collector": 0.6, "local": 0.4, "unknown": 0.5}
TRAFFIC_W = {"high": 1.0, "medium": 0.6, "low": 0.3, "unknown": 0.5}

# (low_upper, medium_upper) on the extent metric
AREA_THRESHOLDS = {
    "pothole": (0.012, 0.045),
    "alligator_crack": (0.04, 0.12),
}
LINEAR_THRESHOLDS = (0.25, 0.5)


def extent_metric(cls, x1, y1, x2, y2, w, h):
    bw, bh = max(0.0, x2 - x1), max(0.0, y2 - y1)
    area_ratio = (bw * bh) / float(max(1, w * h))
    if cls in AREA_THRESHOLDS:
        return area_ratio, area_ratio, AREA_THRESHOLDS[cls]
    major = max(bw / max(1, w), bh / max(1, h))
    return area_ratio, major, LINEAR_THRESHOLDS


def severity(cls, x1, y1, x2, y2, w, h, conf=1.0):
    """Return (area_ratio, severity_label, severity_score 0..1)."""
    x1, y1, x2, y2, conf = float(x1), float(y1), float(x2), float(y2), float(conf)
    area_ratio, m, (lo, mid) = extent_metric(cls, x1, y1, x2, y2, w, h)
    if m < lo:
        label, base = "Low", 0.33 * (m / lo)
    elif m < mid:
        label, base = "Medium", 0.33 + 0.34 * (m - lo) / (mid - lo)
    else:
        label, base = "High", min(1.0, 0.67 + 0.33 * min(1.0, (m - mid) / mid))
    # potholes get a floor: even small potholes are a hazard to two-wheelers
    if cls == "pothole":
        base = max(base, 0.25)
    score = round(base * (0.85 + 0.15 * float(conf)), 4)
    return round(area_ratio, 6), label, score


def severity_from_score(score):
    return "High" if score >= 0.67 else "Medium" if score >= 0.33 else "Low"


def road_factor(road_type="unknown", traffic="unknown"):
    return 0.5 * ROAD_TYPE_W.get(road_type or "unknown", 0.5) + 0.5 * TRAFFIC_W.get(traffic or "unknown", 0.5)


def lane_factor(cx_norm):
    """Wheel-path exposure for road-level cameras: defects near the image centre line sit in the driving lane."""
    if cx_norm is None:
        return 0.6
    d = abs(cx_norm - 0.5) * 2  # 0 centre .. 1 edge
    return round(max(0.35, 1.0 - 0.65 * d), 3)


def risk(cls, severity_score, road_type="unknown", traffic="unknown", report_count=1, trend="new", lane=None,
         breakdown=False):
    sev = 0.45 * severity_score
    haz = 0.20 * CLASS_HAZARD.get(cls, 0.5)
    road = 0.20 * road_factor(road_type, traffic)
    ln = 0.15 * (lane if lane is not None else 0.6)
    rep = min(12, 4 * max(0, (report_count or 1) - 1))
    tr = 8 if trend == "worsening" else 0
    score = round(float(max(0.0, min(100.0, 100 * (sev + haz + road + ln) + rep + tr))), 1)
    if breakdown:
        return score, risk_level(score), {"severity": round(100 * sev, 1), "class_hazard": round(100 * haz, 1),
                                          "road": round(100 * road, 1), "lane_position": round(100 * ln, 1),
                                          "repeat_reports": rep, "worsening": tr}
    return score, risk_level(score)


def risk_level(score):
    return "High" if score >= 70 else "Medium" if score >= 40 else "Low"


RISK_METHOD = {
    "formula": "risk = 100*(0.45*severity + 0.20*class_hazard + 0.20*road_factor + 0.15*lane_position) + repeat_bonus + trend_bonus",
    "lane_position": "1.0 at image centre line (wheel path) down to 0.35 at the edge; 0.6 when unknown",
    "class_hazard": CLASS_HAZARD,
    "road_type_weight": ROAD_TYPE_W,
    "traffic_weight": TRAFFIC_W,
    "road_factor": "0.5*road_type_weight + 0.5*traffic_weight",
    "repeat_bonus": "+4 per additional independent report (max +12)",
    "trend_bonus": "+8 when the defect is worsening",
    "bands": {"High": ">= 70", "Medium": "40-69.9", "Low": "< 40"},
    "severity": {
        "area_classes": AREA_THRESHOLDS,
        "linear_classes_major_axis": LINEAR_THRESHOLDS,
    },
}

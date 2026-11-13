"""Operations layer: repair cost estimates, budget optimisation, alerts, weather risk, OSM road type,
complaint / authority PDF reports and a mock "send to authority".

Repair cost model (all rates live in RATES and are planning assumptions, not quotes):
  m_per_pixel: dashcam frame -> a 3.5 m lane spans ~60% of the frame width at the box's row,
               so m_per_px = 3.5 / (0.60 * frame_width);
               close-up photo (box area > 18% of frame) -> frame shows ~1.5 m width, m_per_px = 1.5 / frame_width
  area_m2   = box_w_px * box_h_px * fill_factor * m_per_px^2   (fill_factor 0.785 = ellipse inside the box)
  depth     = by severity (Minor 2 cm, Moderate 4, Severe 6, Critical 9; legacy Low 2, Medium 5, High 8)
  volume_m3 = area_m2 * depth_m
  material  = cold mix if volume < 0.05 m3 else hot mix, cost = volume * rate
  labour    = 600 + 900 * area_m2
  traffic   = traffic management by road type
  total     = (material + labour + traffic) * 1.10 contingency
  cracks    : crack sealing 350 INR per metre of crack (major axis of the box) + traffic, * contingency
  manhole   : fixed 2500 reset; debris: fixed 800 clearance; speed_breaker / barricade are not damage (excluded)
"""
import math
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
import numpy as np
from fastapi import Body, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy import JSON, Column, DateTime, Float, Integer, String, Text

from . import auth, config, events, reports, scoring
from .db import Base, Defect, DefectHistory, Detection, Inspection, SessionLocal, engine, now
from .geo import haversine_m

UA = {"User-Agent": "Disha AI/1.0 (municipal road monitoring)"}
HTTP_TIMEOUT = float(os.getenv("RD_OPS_HTTP_TIMEOUT", "12"))
OVERPASS_URL = os.getenv("RD_OVERPASS_URL", "https://overpass-api.de/api/interpreter")
OVERPASS_TIMEOUT = float(os.getenv("RD_OVERPASS_TIMEOUT", "45"))  # public Overpass is often slow

# ---------------------------------------------------------------- rates (assumptions)
# Cost of delay: assumed weekly growth of the repair bill if the defect is left alone (assumptions, not official data).
DELAY_GROWTH_PER_WEEK = {"pothole": 0.06, "alligator_crack": 0.08, "transverse_crack": 0.04, "longitudinal_crack": 0.03,
                         "manhole": 0.02, "debris": 0.0, "speed_breaker": 0.0, "barricade": 0.0}
DELAY_ROAD_MULT = {"highway": 1.5, "arterial": 1.3, "collector": 1.1, "local": 1.0, "unknown": 1.0}
DELAY_TREND_MULT = {"worsening": 1.5, "new": 1.0, "stable": 1.0, "improving": 0.7}

RATES = {
    "currency": "INR",
    "cold_mix_per_m3": 9000,
    "hot_mix_per_m3": 7000,
    "cold_mix_max_volume_m3": 0.05,
    "labour_fixed": 600,
    "labour_per_m2": 900,
    "traffic_management": {"highway": 1500, "arterial": 1000, "collector": 600, "local": 300, "unknown": 500},
    "contingency": 0.10,
    "crack_sealing_per_m": 350,
    "manhole_reset": 2500,
    "debris_clearance": 800,
    "depth_cm": {"Minor": 2, "Moderate": 4, "Severe": 6, "Critical": 9, "Low": 2, "Medium": 5, "High": 8},
    "default_depth_cm": 4,
    "lane_width_m": 3.5,
    "lane_frame_fraction": 0.60,
    "closeup_box_fraction": 0.18,
    "closeup_frame_width_m": 1.5,
    "fill_factor": 0.785,
    "min_area_m2": 0.05,
    "max_area_m2": 25.0,
    "default_area_m2": 0.5,
    "default_crack_length_m": 1.5,
}
RATES_NOTES = {
    "status": "All rates are planning assumptions for prioritisation, not tender quotes. Edit RATES in ops.py.",
    "scale": "Dashcam frames: a 3.5 m lane spans ~60% of frame width, m_per_px = 3.5 / (0.6 * width). "
             "Close-ups (box > 18% of frame): frame shows ~1.5 m, m_per_px = 1.5 / width.",
    "area": "area_m2 = box_w * box_h * fill_factor(0.785, ellipse) * m_per_px^2, clamped to [0.05, 25] m2. "
            "Falls back to 0.5 m2 when no box or frame size is stored.",
    "depth": "Depth assumed from severity (cm): Minor 2, Moderate 4, Severe 6, Critical 9; legacy Low 2, Medium 5, High 8.",
    "material": "cold mix (9000 INR/m3) when volume < 0.05 m3, else hot mix (7000 INR/m3).",
    "labour": "600 fixed + 900 per m2.",
    "traffic": "Traffic management by road type: highway 1500, arterial 1000, collector 600, local 300, unknown 500.",
    "total": "(material + labour + traffic) * 1.10 contingency.",
    "cracks": "Crack sealing 350 INR per metre (box major axis) + traffic management, plus contingency.",
    "fixed": "manhole reset 2500, debris clearance 800. speed_breaker and barricade are not damage and are excluded.",
}
CRACKS = {"alligator_crack", "transverse_crack", "longitudinal_crack"}
NON_DAMAGE = {"speed_breaker", "barricade"}
HAZARD_TEXT = {
    "pothole": "It is a risk to two-wheelers and cars",
    "alligator_crack": "It weakens the road surface and will develop into potholes",
    "transverse_crack": "It lets water into the road base and will widen over time",
    "longitudinal_crack": "It lets water into the road base and will widen over time",
    "manhole": "A sunken or open manhole is a serious hazard to two-wheelers and pedestrians",
    "debris": "Debris on the carriageway can cause skids and collisions",
}


# ---------------------------------------------------------------- tables
class Alert(Base):
    __tablename__ = "alerts"
    id = Column(Integer, primary_key=True)
    type = Column(String(30), index=True)
    level = Column(String(10), index=True)  # critical | warning | info
    defect_id = Column(Integer, index=True, nullable=True)
    uid = Column(String(20))
    message = Column(Text)
    status = Column(String(20), default="open", index=True)  # open | acknowledged | resolved
    lat = Column(Float, nullable=True)
    lon = Column(Float, nullable=True)
    created_at = Column(DateTime, default=now)
    updated_at = Column(DateTime, default=now)
    dedupe_key = Column(String(160), unique=True, index=True)


class RoadCache(Base):
    __tablename__ = "road_cache"
    key = Column(String(40), primary_key=True)  # "lat4,lon4"
    road_type = Column(String(20))
    osm_highway = Column(String(40))
    name = Column(String(255))
    fetched_at = Column(DateTime, default=now)


class WeatherCache(Base):
    __tablename__ = "weather_cache"
    key = Column(String(40), primary_key=True)  # "lat2,lon2"
    payload = Column(JSON)
    fetched_at = Column(DateTime, default=now)


# ---------------------------------------------------------------- helpers
def _pretty(cls):
    return (cls or "defect").replace("_", " ")


def _loc(d):
    return f"({d.lat:.5f}, {d.lon:.5f})" if d.lat is not None and d.lon is not None else "an unrecorded location"


def _ref_detection(d: Defect) -> Optional[Detection]:
    """Latest non-rejected detection with a usable box and frame size."""
    best = None
    for det in d.detections:
        if det.verification == "rejected":
            continue
        i = det.inspection
        if not (i and i.width and i.height and det.x2 is not None and det.x1 is not None):
            continue
        if best is None or (det.created_at or datetime.min) >= (best.created_at or datetime.min):
            best = det
    return best


def _latest_detection(d: Defect) -> Optional[Detection]:
    dets = [x for x in d.detections if x.verification != "rejected"] or list(d.detections)
    return max(dets, key=lambda x: x.created_at or datetime.min) if dets else None


def _scale(det: Optional[Detection]):
    """Return (box_w_px, box_h_px, m_per_px, mode) or None."""
    if det is None:
        return None
    i = det.inspection
    W, H = float(i.width), float(i.height)
    bw, bh = max(0.0, det.x2 - det.x1), max(0.0, det.y2 - det.y1)
    if bw <= 0 or bh <= 0:
        return None
    frac = (bw * bh) / max(1.0, W * H)
    if frac > RATES["closeup_box_fraction"]:
        return bw, bh, RATES["closeup_frame_width_m"] / W, "closeup"
    return bw, bh, RATES["lane_width_m"] / (RATES["lane_frame_fraction"] * W), "dashcam"


def estimate(d: Defect) -> Optional[dict]:
    """Repair cost row for one defect, None for non-damage classes."""
    cls = d.class_name or "pothole"
    if cls in NON_DAMAGE:
        return None
    sc = _scale(_ref_detection(d))
    traffic_cost = float(RATES["traffic_management"].get(d.road_type or "unknown", RATES["traffic_management"]["unknown"]))
    k = 1.0 + RATES["contingency"]
    area = depth_cm = volume = 0.0
    length = None
    labour = material_cost = 0.0
    basis = "box" if sc else "default"
    if sc:
        bw, bh, mpp, mode = sc
        area = bw * bh * RATES["fill_factor"] * mpp * mpp
        area = min(RATES["max_area_m2"], max(RATES["min_area_m2"], area))
        basis = mode
    else:
        area = RATES["default_area_m2"]
    if cls == "manhole":
        material, material_cost, traffic_cost, total = "manhole reset", float(RATES["manhole_reset"]), 0.0, float(RATES["manhole_reset"])
    elif cls == "debris":
        material, material_cost, traffic_cost, total = "debris clearance", float(RATES["debris_clearance"]), 0.0, float(RATES["debris_clearance"])
    elif cls in CRACKS:
        length = max(bw, bh) * mpp if sc else RATES["default_crack_length_m"]
        length = round(max(0.3, length), 2)
        material = "crack sealant"
        material_cost = length * RATES["crack_sealing_per_m"]
        total = (material_cost + traffic_cost) * k
    else:  # pothole and anything else area-like
        depth_cm = float(RATES["depth_cm"].get(d.severity or "", RATES["default_depth_cm"]))
        volume = area * depth_cm / 100.0
        if volume < RATES["cold_mix_max_volume_m3"]:
            material, rate = "cold mix", RATES["cold_mix_per_m3"]
        else:
            material, rate = "hot mix", RATES["hot_mix_per_m3"]
        material_cost = volume * rate
        labour = RATES["labour_fixed"] + RATES["labour_per_m2"] * area
        total = (material_cost + labour + traffic_cost) * k
    return {
        "defect_id": d.id, "uid": d.uid, "class_name": cls, "severity": d.severity,
        "risk_score": round(float(d.risk_score or 0), 1), "risk_level": d.risk_level,
        "area_m2": round(area, 3), "depth_cm": depth_cm, "volume_m3": round(volume, 4),
        "length_m": length, "material": material, "material_cost": round(material_cost),
        "labour_cost": round(labour), "traffic_cost": round(traffic_cost), "total_cost": round(total),
        "lat": d.lat, "lon": d.lon, "crop_url": f"/media/crops/{d.best_crop}" if d.best_crop else None,
        "road_type": d.road_type or "unknown", "status": d.status, "basis": basis,
        **delay_fields(d, total),
    }


def delay_fields(d, total):
    """Weekly and 30-day cost of waiting: repair cost x weekly growth x road traffic x trend multiplier."""
    g = DELAY_GROWTH_PER_WEEK.get(d.class_name, 0.04) * DELAY_ROAD_MULT.get(d.road_type or "unknown", 1.0)         * DELAY_TREND_MULT.get(d.trend or "new", 1.0)
    week = total * g
    return {"delay_weekly": round(week), "delay_30d": round(total * ((1 + g) ** (30 / 7.0) - 1)),
            "delay_growth_pct_week": round(g * 100, 1)}


def cost_rows(s, status: str = "active"):
    q = s.query(Defect)
    if status and status != "all":
        q = q.filter(Defect.status == status)
    else:
        q = q.filter(Defect.status != "rejected")
    rows = [r for r in (estimate(d) for d in q.order_by(Defect.risk_score.desc()).all()) if r]
    return rows


def optimise(rows, budget: float, value_key: str = "risk_score"):
    """0/1 knapsack on risk_score with costs in units of 100 INR; greedy by risk/cost above 2000 items."""
    budget = max(0.0, float(budget))
    items = [r for r in rows if r["total_cost"] > 0 and r[value_key] > 0]
    if sum(r["total_cost"] for r in items) <= budget:
        chosen = items
    elif len(items) > 2000 or budget / 100 * len(items) > 6e7:
        chosen, spent = [], 0.0
        for r in sorted(items, key=lambda r: r[value_key] / r["total_cost"], reverse=True):
            if spent + r["total_cost"] <= budget:
                chosen.append(r)
                spent += r["total_cost"]
    else:
        cap = int(budget // 100)
        w = [int(math.ceil(r["total_cost"] / 100.0)) for r in items]
        v = np.array([r[value_key] for r in items], dtype=np.float64)
        dp = np.zeros(cap + 1, dtype=np.float64)
        keep = np.zeros((len(items), cap + 1), dtype=bool)
        for k, wk in enumerate(w):
            if wk > cap:
                continue
            cand = dp[:cap + 1 - wk] + v[k]
            better = cand > dp[wk:]
            keep[k, wk:] = better
            dp[wk:] = np.where(better, cand, dp[wk:])
        chosen, c = [], cap
        for k in range(len(items) - 1, -1, -1):
            if keep[k, c]:
                chosen.append(items[k])
                c -= w[k]
        chosen.reverse()
    chosen = sorted(chosen, key=lambda r: r[value_key], reverse=True)
    total = sum(r["total_cost"] for r in chosen)
    return {"budget": budget, "selected": chosen, "total_cost": round(total),
            "risk_covered": round(sum(r["risk_score"] for r in chosen), 1),
            "risk_total": round(sum(r["risk_score"] for r in rows), 1), "left": round(budget - total)}


# ---------------------------------------------------------------- weather (Open-Meteo)
def _weather_risk(rain, prob):
    if rain is None:
        return "unknown"
    if rain > 10 or (prob or 0) >= 85:
        return "high"
    if rain > 2 or (prob or 0) >= 50:
        return "medium"
    return "low"


def weather(lat: float, lon: float, s=None) -> dict:
    key = f"{round(lat, 2):.2f},{round(lon, 2):.2f}"
    own = s is None
    s = s or SessionLocal()
    try:
        c = s.get(WeatherCache, key)
        if c and c.fetched_at and now() - c.fetched_at < timedelta(hours=1):
            return dict(c.payload, cached=True)
        try:
            r = httpx.get("https://api.open-meteo.com/v1/forecast",
                          params={"latitude": round(lat, 2), "longitude": round(lon, 2),
                                  "hourly": "precipitation,precipitation_probability", "forecast_days": 2,
                                  "timezone": "UTC"}, headers=UA, timeout=HTTP_TIMEOUT)
            r.raise_for_status()
            h = r.json().get("hourly", {})
            times = h.get("time", [])
            cur = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:00")
            start = next((k for k, t in enumerate(times) if t >= cur), 0)
            pr = [x or 0 for x in h.get("precipitation", [])[start:start + 24]]
            pp = [x or 0 for x in h.get("precipitation_probability", [])[start:start + 24]]
            rain = round(float(sum(pr)), 1)
            prob = int(max(pp)) if pp else None
            out = {"rain_mm_24h": rain, "max_precip_probability": prob, "risk": _weather_risk(rain, prob),
                   "source": "open-meteo"}
        except Exception as e:  # network / API failure: degrade gracefully, do not cache
            return {"rain_mm_24h": None, "max_precip_probability": None, "risk": "unknown",
                    "source": "open-meteo", "error": type(e).__name__}
        if c is None:
            c = WeatherCache(key=key)
            s.add(c)
        c.payload, c.fetched_at = out, now()
        try:
            s.commit()
        except Exception:
            s.rollback()
        return out
    finally:
        if own:
            s.close()


# ---------------------------------------------------------------- road type (OSM Overpass)
OSM_MAP = {
    "motorway": "highway", "motorway_link": "highway", "trunk": "highway", "trunk_link": "highway",
    "primary": "arterial", "primary_link": "arterial", "secondary": "arterial", "secondary_link": "arterial",
    "tertiary": "collector", "tertiary_link": "collector",
    "residential": "local", "service": "local", "unclassified": "local", "living_street": "local", "road": "local",
}
_overpass_lock = threading.Lock()
_overpass_last = [0.0]


def _seg_dist_m(lat, lon, a, b):
    """Approx distance (m) from point to segment a-b using a local equirectangular projection."""
    kx = 111320.0 * math.cos(math.radians(lat))
    ky = 110540.0
    ax, ay = (a["lon"] - lon) * kx, (a["lat"] - lat) * ky
    bx, by = (b["lon"] - lon) * kx, (b["lat"] - lat) * ky
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    t = 0.0 if L == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / L))
    px, py = ax + t * dx, ay + t * dy
    return math.hypot(px, py)


def road_lookup(lat: float, lon: float, s=None) -> dict:
    """Returns {"road_type", "osm_highway", "name", "cached"?, "fetched": bool}."""
    key = f"{round(lat, 4):.4f},{round(lon, 4):.4f}"
    own = s is None
    s = s or SessionLocal()
    try:
        c = s.get(RoadCache, key)
        if c:
            return {"road_type": c.road_type, "osm_highway": c.osm_highway, "name": c.name, "cached": True,
                    "fetched": False}
        q = f'[out:json][timeout:40];way(around:30,{lat:.6f},{lon:.6f})[highway];out tags geom;'
        try:
            with _overpass_lock:
                wait = 1.0 - (time.time() - _overpass_last[0])
                if wait > 0:
                    time.sleep(wait)
                _overpass_last[0] = time.time()
                r = httpx.get(OVERPASS_URL, params={"data": q}, headers=UA, timeout=OVERPASS_TIMEOUT)
            r.raise_for_status()
            ways = r.json().get("elements", [])
        except Exception as e:
            return {"road_type": "unknown", "osm_highway": None, "name": None, "error": type(e).__name__,
                    "fetched": True}
        best, best_d = None, 1e18
        for w in ways:
            tag = (w.get("tags") or {}).get("highway")
            if tag not in OSM_MAP:
                continue
            g = w.get("geometry") or []
            dist = min((_seg_dist_m(lat, lon, g[k], g[k + 1]) for k in range(len(g) - 1)), default=1e17)
            if dist < best_d:
                best, best_d = w, dist
        if best:
            tags = best.get("tags") or {}
            out = {"road_type": OSM_MAP[tags["highway"]], "osm_highway": tags["highway"],
                   "name": tags.get("name") or tags.get("ref")}
        else:
            raw = next(((w.get("tags") or {}).get("highway") for w in ways), None)
            out = {"road_type": "unknown", "osm_highway": raw, "name": None}
        s.add(RoadCache(key=key, road_type=out["road_type"], osm_highway=out["osm_highway"], name=out["name"],
                        fetched_at=now()))
        try:
            s.commit()
        except Exception:
            s.rollback()
        return dict(out, fetched=True)
    finally:
        if own:
            s.close()


# ---------------------------------------------------------------- alerts
LEVEL_ORDER = {"critical": 0, "warning": 1, "info": 2}
_scan_lock = threading.Lock()
WEATHER_MAX_LOCATIONS = 20
NEW_DEFECT_WINDOW = timedelta(days=3)


def ser_alert(a: Alert):
    return {"id": a.id, "type": a.type, "level": a.level, "defect_id": a.defect_id, "uid": a.uid,
            "message": a.message, "status": a.status, "lat": a.lat, "lon": a.lon, "created_at": a.created_at}


def _summary(s):
    rows = s.query(Alert.level).filter(Alert.status == "open").all()
    out = {"open": len(rows), "critical": 0, "warning": 0, "info": 0}
    for (lvl,) in rows:
        if lvl in out:
            out[lvl] += 1
    return out


def _first(d):
    return f"{d.first_seen:%Y-%m-%d}" if d.first_seen else "unknown"


def _clusters(defs, radius=150.0):
    """Connected groups of defects within `radius` m of each other (grid bucketed)."""
    cell = radius / 111000.0
    grid = {}
    for d in defs:
        grid.setdefault((int(d.lat // cell), int(d.lon // cell)), []).append(d)
    parent = {d.id: d.id for d in defs}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    max_lat = max((abs(d.lat) for d in defs), default=0.0)
    ny = int(math.ceil(1.0 / max(0.05, math.cos(math.radians(min(89.0, max_lat))))))  # lon cells span less ground
    for d in defs:
        gx, gy = int(d.lat // cell), int(d.lon // cell)
        for dx in (-1, 0, 1):
            for dy in range(-ny, ny + 1):
                for o in grid.get((gx + dx, gy + dy), []):
                    if o.id > d.id and haversine_m(d.lat, d.lon, o.lat, o.lon) <= radius:
                        parent[find(o.id)] = find(d.id)
    groups = {}
    for d in defs:
        groups.setdefault(find(d.id), []).append(d)
    return [g for g in groups.values() if len(g) >= 3]


def scan(with_weather: bool = True) -> dict:
    with _scan_lock:
        s = SessionLocal()
        try:
            return _scan(s, with_weather)
        finally:
            s.close()


def _scan(s, with_weather):
    existing = {a.dedupe_key: a for a in s.query(Alert).all()}
    wanted = {}  # dedupe_key -> dict
    t_now = now()
    defects = s.query(Defect).filter(Defect.status != "rejected").all()
    active = [d for d in defects if d.status == "active"]

    def want(type_, level, d, state, msg):
        key = f"{type_}:{d.id}:{state}"
        wanted[key] = {"type": type_, "level": level, "defect_id": d.id, "uid": d.uid, "message": msg,
                       "lat": d.lat, "lon": d.lon}

    for d in defects:
        name = _pretty(d.class_name).capitalize()
        risk = float(d.risk_score or 0)
        if d.status == "repaired":
            want("repaired", "info", d, "repaired",
                 f"REPAIRED: {name} {d.uid} near {_loc(d)} is no longer observed. First reported {_first(d)}.")
            continue
        if risk >= 70:
            want("high_risk", "critical", d, "high",
                 f"HIGH RISK: {name} {d.uid} near {_loc(d)}. Severity {d.severity}, risk {risk:.0f}. "
                 f"First reported {_first(d)}.")
        if d.first_seen and t_now - d.first_seen <= NEW_DEFECT_WINDOW:
            want("new_defect", "info", d, "new",
                 f"NEW: {name} {d.uid} detected near {_loc(d)}. Severity {d.severity}, risk {risk:.0f}.")
        if (d.report_count or 1) > 1:
            want("duplicate", "info", d, str(d.report_count),
                 f"DUPLICATE REPORTS: {name} {d.uid} near {_loc(d)} has been reported {d.report_count} times. "
                 f"Merged into one defect.")
        if d.trend == "worsening":
            stamp = f"{d.last_seen:%Y%m%d%H%M}" if d.last_seen else "x"
            want("worsening", "warning", d, stamp,
                 f"WORSENING: {name} {d.uid} near {_loc(d)} got worse at the last inspection. "
                 f"Severity {d.severity}, risk {risk:.0f}.")
        if d.verified and d.first_seen and t_now - d.first_seen > timedelta(days=14):
            days = (t_now - d.first_seen).days
            want("overdue", "warning", d, "overdue",
                 f"OVERDUE: Verified {_pretty(d.class_name)} {d.uid} near {_loc(d)} is still unrepaired after "
                 f"{days} days. First reported {_first(d)}.")
        for det in d.detections:
            if det.verification == "pending" and det.confidence is not None and det.confidence < 0.4:
                key = f"low_confidence:{d.id}:det{det.id}"
                wanted[key] = {"type": "low_confidence", "level": "info", "defect_id": d.id, "uid": d.uid,
                               "lat": d.lat, "lon": d.lon,
                               "message": f"VERIFY: Detection #{det.id} of {_pretty(det.class_name)} {d.uid} has low "
                                          f"confidence ({det.confidence:.2f}). Please confirm or reject."}

    geo = [d for d in active if d.lat is not None and d.lon is not None]
    for g in _clusters(geo):
        anchor = min(g, key=lambda x: x.id)
        uids = ", ".join(x.uid for x in sorted(g, key=lambda x: -(x.risk_score or 0))[:6])
        want("repeat_road", "warning", anchor, f"n{len(g)}",
             f"REPEAT DAMAGE: {len(g)} active defects within 150 m of each other near {_loc(anchor)} ({uids}). "
             f"Consider resurfacing the stretch.")

    if with_weather:
        hot = [d for d in geo if (d.risk_score or 0) >= 70 or d.severity in ("Critical", "High")]
        by_loc = {}
        for d in hot:
            by_loc.setdefault((round(d.lat, 2), round(d.lon, 2)), []).append(d)
        day = f"{t_now:%Y%m%d}"
        for (la, lo), ds in sorted(by_loc.items(), key=lambda kv: -max(x.risk_score or 0 for x in kv[1]))[
                :WEATHER_MAX_LOCATIONS]:
            w = weather(la, lo, s)
            if w.get("rain_mm_24h") is not None and w["rain_mm_24h"] > 10:
                for d in ds:
                    want("weather_risk", "warning", d, day,
                         f"RAIN RISK: {w['rain_mm_24h']:.0f} mm rain forecast in the next 24 h near {_loc(d)}. "
                         f"{_pretty(d.class_name).capitalize()} {d.uid} (risk {d.risk_score:.0f}) may worsen "
                         f"or fill with water. Repair or barricade before rain.")

    created = []
    for key, a in wanted.items():
        if key in existing:
            continue
        row = Alert(dedupe_key=key, status="open", created_at=t_now, updated_at=t_now, **a)
        s.add(row)
        created.append(row)

    # auto-resolve alerts whose condition no longer holds
    resolved = 0
    still = set(wanted)
    by_id = {d.id: d for d in defects}
    for key, a in existing.items():
        if a.status == "resolved" or a.type in ("repaired", "new_defect", "duplicate"):
            continue
        d = by_id.get(a.defect_id)
        gone = d is None or d.status != "active"
        if a.type == "weather_risk":
            gone = gone or key not in still and not key.endswith(f"{t_now:%Y%m%d}")
        elif a.type == "repeat_road":
            gone = gone or key not in still
        elif not gone:
            gone = key not in still
        if gone:
            a.status, a.updated_at = "resolved", t_now
            resolved += 1
    try:
        s.commit()
    except Exception:
        s.rollback()
        raise
    for row in created:
        events.publish("alert.created", ser_alert(row))
    out = _summary(s)
    out.update({"created": len(created), "auto_resolved": resolved})
    return out


def _scan_loop(interval):
    time.sleep(5)
    while True:
        try:
            scan()
        except Exception as e:  # never let the loop die
            print(f"[ops] alert scan failed: {e!r}")
        time.sleep(interval)


# ---------------------------------------------------------------- complaint text / report data
def complaint_text(d: Defect) -> str:
    when = d.first_seen or now()
    sev = d.severity or "reported"
    cls = _pretty(d.class_name)
    art = "An" if sev[:1].upper() in "AEIOU" else "A"
    hazard = HAZARD_TEXT.get(d.class_name, "It is a hazard to road users")
    extra = f" It has been reported {d.report_count} times." if (d.report_count or 1) > 1 else ""
    return (f"Complaint {d.uid}: {art} {sev} {cls} was detected near {_loc(d)} on {when:%d %b %Y}. "
            f"{hazard}.{extra} Please inspect and repair.")


def _get_defect(s, defect_id) -> Defect:
    d = s.get(Defect, defect_id)
    if d is None:
        raise HTTPException(404, "defect not found")
    return d


def _report_ctx(s, d: Defect, request: Request) -> dict:
    base = str(request.base_url).rstrip("/")
    det = _latest_detection(d)
    insp = det.inspection if det else None
    annotated = insp.annotated_path if insp and insp.annotated_path and os.path.exists(insp.annotated_path) else None
    crop = None
    if d.best_crop and (config.CROPS / d.best_crop).exists():
        crop = str(config.CROPS / d.best_crop)
    cost = estimate(d)
    ranked = [x.id for x in s.query(Defect.id).filter(Defect.status == "active")
              .order_by(Defect.risk_score.desc()).all()]
    rank = (ranked.index(d.id) + 1) if d.id in ranked else None
    _, _, parts = scoring.risk(d.class_name, d.severity_score or 0, d.road_type, d.traffic_level, d.report_count,
                               d.trend, breakdown=True)
    history = s.query(DefectHistory).filter(DefectHistory.defect_id == d.id).order_by(
        DefectHistory.observed_at).all()
    alerts = s.query(Alert).filter(Alert.defect_id == d.id, Alert.status != "resolved").order_by(
        Alert.created_at.desc()).all()
    return {"defect": d, "detection": det, "inspection": insp, "annotated": annotated, "crop": crop, "cost": cost,
            "rank": rank, "active_total": len(ranked), "breakdown": parts, "history": history,
            "alerts": [ser_alert(a) for a in alerts], "text": complaint_text(d),
            "track_url": f"{base}/track/{d.uid}", "detections": sorted(d.detections, key=lambda x: x.id)}


# ---------------------------------------------------------------- routes
def register(app):
    Base.metadata.create_all(engine, tables=[Alert.__table__, RoadCache.__table__, WeatherCache.__table__])
    interval = float(os.getenv("RD_ALERT_SCAN_S", "60"))

    @app.on_event("startup")
    def _start_scanner():
        if interval > 0:
            threading.Thread(target=_scan_loop, args=(interval,), daemon=True, name="alert-scan").start()

    @app.get("/api/ops/rates", dependencies=[Depends(auth.require_officer)])
    def get_rates():
        return dict(RATES, notes=RATES_NOTES)

    @app.get("/api/ops/costs")
    def get_costs(status: str = "active"):
        s = SessionLocal()
        try:
            return cost_rows(s, status)
        finally:
            s.close()

    @app.post("/api/ops/budget")
    def post_budget(body: dict = Body(...)):
        try:
            budget = float(body.get("budget"))
        except (TypeError, ValueError):
            raise HTTPException(422, "budget must be a number")
        if budget < 0:
            raise HTTPException(422, "budget must be >= 0")
        s = SessionLocal()
        try:
            objective = str(body.get("objective", "risk"))
            key = "delay_weekly" if objective == "delay" else "risk_score"
            out = optimise(cost_rows(s, "active"), budget, key)
            out["objective"] = "delay" if key == "delay_weekly" else "risk"
            out["delay_weekly_avoided"] = sum(r["delay_weekly"] for r in out["selected"])
            return out
        finally:
            s.close()

    @app.get("/api/ops/weather")
    def get_weather(lat: float, lon: float):
        out = weather(lat, lon)
        out.pop("cached", None)
        return out

    @app.get("/api/ops/road")
    def get_road(lat: float, lon: float):
        r = road_lookup(lat, lon)
        return {"road_type": r["road_type"], "osm_highway": r["osm_highway"], "name": r["name"]}

    @app.post("/api/ops/enrich-roads")
    def enrich_roads(limit: int = 30, _u=Depends(auth.require_officer)):
        s = SessionLocal()
        try:
            todo = s.query(Defect).filter(Defect.status == "active", Defect.lat.isnot(None), Defect.lon.isnot(None),
                                          (Defect.road_type.is_(None)) | (Defect.road_type == "unknown")).limit(
                max(1, min(limit, 200))).all()
            updated, failed, out = 0, 0, []
            for d in todo:
                r = road_lookup(d.lat, d.lon, s)  # Overpass calls are throttled to 1 per second inside
                if r.get("error"):
                    failed += 1
                    continue
                if r["road_type"] != "unknown":
                    d.road_type = r["road_type"]
                    from .pipeline import refresh_defect_risk
                    refresh_defect_risk(d)
                    updated += 1
                    out.append({"defect_id": d.id, "uid": d.uid, "road_type": d.road_type,
                                "osm_highway": r["osm_highway"], "name": r["name"], "risk_score": d.risk_score})
            s.commit()
            for x in out:
                events.publish("defect.updated", {"id": x["defect_id"], "uid": x["uid"], "road_type": x["road_type"],
                                                  "risk_score": x["risk_score"]})
            return {"checked": len(todo), "updated": updated, "failed": failed, "defects": out}
        finally:
            s.close()

    # alerts: /scan and /summary are declared before /{alert_id}
    @app.post("/api/alerts/scan")
    def alerts_scan(_u=Depends(auth.require_officer)):
        return scan()

    @app.get("/api/alerts/summary", dependencies=[Depends(auth.require_officer)])
    def alerts_summary():
        s = SessionLocal()
        try:
            return _summary(s)
        finally:
            s.close()

    @app.get("/api/alerts", dependencies=[Depends(auth.require_officer)])
    def alerts_list(status: str = "open", limit: int = 500):
        s = SessionLocal()
        try:
            q = s.query(Alert)
            if status != "all":
                if status not in ("open", "acknowledged", "resolved"):
                    raise HTTPException(422, "status must be open|acknowledged|resolved|all")
                q = q.filter(Alert.status == status)
            rows = q.order_by(Alert.created_at.desc(), Alert.id.desc()).limit(max(1, min(limit, 5000))).all()
            rows.sort(key=lambda a: LEVEL_ORDER.get(a.level, 9))  # stable: keeps newest first inside a level
            return [ser_alert(a) for a in rows]
        finally:
            s.close()

    @app.post("/api/alerts/{alert_id}")
    def alerts_update(alert_id: int, body: dict = Body(...), user=Depends(auth.require_officer)):
        st = body.get("status")
        if st not in ("acknowledged", "resolved", "open"):
            raise HTTPException(422, "status must be acknowledged|resolved")
        s = SessionLocal()
        try:
            a = s.get(Alert, alert_id)
            if a is None:
                raise HTTPException(404, "alert not found")
            a.status, a.updated_at = st, now()
            s.commit()
            out = ser_alert(a)
            events.publish("alert.updated", out)
            return out
        finally:
            s.close()

    # reports
    @app.get("/api/reports/complaint/{defect_id}.pdf", dependencies=[Depends(auth.require_officer)])
    def complaint_pdf(defect_id: int, request: Request):
        s = SessionLocal()
        try:
            d = _get_defect(s, defect_id)
            pdf = reports.complaint_pdf(_report_ctx(s, d, request))
        finally:
            s.close()
        return Response(pdf, media_type="application/pdf",
                        headers={"Content-Disposition": f'inline; filename="complaint_{d.uid}.pdf"'})

    @app.get("/api/reports/authority/{defect_id}.pdf", dependencies=[Depends(auth.require_officer)])
    def authority_pdf(defect_id: int, request: Request):
        s = SessionLocal()
        try:
            d = _get_defect(s, defect_id)
            pdf = reports.authority_pdf(_report_ctx(s, d, request), RATES)
        finally:
            s.close()
        return Response(pdf, media_type="application/pdf",
                        headers={"Content-Disposition": f'inline; filename="authority_{d.uid}.pdf"'})

    @app.get("/api/reports/evidence/{defect_id}.pdf", dependencies=[Depends(auth.require_officer)])
    def evidence_pdf(defect_id: int, request: Request):
        s = SessionLocal()
        try:
            d = _get_defect(s, defect_id)
            pdf = reports.evidence_pdf(_report_ctx(s, d, request))
        finally:
            s.close()
        return Response(pdf, media_type="application/pdf",
                        headers={"Content-Disposition": f'inline; filename="evidence_{d.uid}.pdf"'})

    @app.get("/api/ops/complaint-text/{defect_id}", dependencies=[Depends(auth.require_officer)])
    def get_complaint_text(defect_id: int):
        s = SessionLocal()
        try:
            return {"text": complaint_text(_get_defect(s, defect_id))}
        finally:
            s.close()

    @app.post("/api/ops/send/{defect_id}")
    def send_mock(defect_id: int, request: Request, user=Depends(auth.require_officer)):
        s = SessionLocal()
        try:
            d = _get_defect(s, defect_id)
            base = str(request.base_url).rstrip("/")
            subject = f"Road damage complaint {d.uid}: {d.severity} {_pretty(d.class_name)}"
            body = (complaint_text(d) + f"\n\nTrack: {base}/track/{d.uid}"
                    f"\nComplaint report: {base}/api/reports/complaint/{d.id}.pdf"
                    f"\nAuthority report: {base}/api/reports/authority/{d.id}.pdf")
            out = {"sent": False, "mock": True, "to": "roads department (mock)", "subject": subject, "body": body}
            events.publish("complaint.sent_mock", {"defect_id": d.id, "uid": d.uid, "subject": subject,
                                                   "by": (user or {}).get("email")})
            return out
        finally:
            s.close()

"""Road-quality aware route planning: pick the smoothest road, the way traffic apps pick the fastest.

Flow
  1. Alternative routes between two points come from OSRM (OpenStreetMap routing, free demo server).
  2. Every route is scored against the LIVE defect register: each open defect within CORRIDOR_M metres of the route
     counts, weighted by its risk score and damage type. A report filed a minute ago changes the advice immediately.
  3. Each route gets a penalty in minutes (a risk-75 pothole costs about 3 minutes of comfort and safety), and the
     recommended route is the one with the lowest driving time plus penalty.

Penalty per defect (minutes) = PENALTY_MIN_AT_FULL_RISK x risk/100 x class weight.
Endpoint: GET /api/routeplan?origin=lat,lon|place&dest=lat,lon|place
"""
import math
import os
import re
import threading
import time
from typing import Optional

import httpx
import numpy as np
from fastapi import HTTPException, Query
from sqlalchemy import Column, DateTime, Float, String

from . import scoring
from .db import Base, Defect, SessionLocal, engine, now

OSRM_URL = os.getenv("RD_OSRM_URL", "https://router.project-osrm.org").rstrip("/")
UA = "Disha AI/1.0 (municipal road monitoring)"
CORRIDOR_M = float(os.getenv("RD_ROUTE_CORRIDOR_M", "15"))
PENALTY_MIN_AT_FULL_RISK = float(os.getenv("RD_ROUTE_PENALTY_MIN", "4"))
IGNORED = {"speed_breaker", "barricade"}
CLASS_W = {"pothole": 1.0, "alligator_crack": 0.7, "manhole": 0.8, "debris": 0.5, "transverse_crack": 0.35,
           "longitudinal_crack": 0.3}

_geo_lock = threading.Lock()
_last_geo = [0.0]


class RouteGeocode(Base):
    __tablename__ = "route_geocode"
    q = Column(String(255), primary_key=True)
    lat = Column(Float)
    lon = Column(Float)
    name = Column(String(255))
    created_at = Column(DateTime, default=now)


def _parse_point(text: str):
    m = re.match(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$", text or "")
    if m:
        lat, lon = float(m.group(1)), float(m.group(2))
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            return lat, lon, f"{lat:.5f}, {lon:.5f}"
    return None


def geocode(text: str):
    p = _parse_point(text)
    if p:
        return p
    key = " ".join((text or "").lower().split())[:250]
    if not key:
        raise HTTPException(400, "Enter a start and a destination")
    s = SessionLocal()
    try:
        c = s.get(RouteGeocode, key)
        if c:
            if c.lat is None:
                raise HTTPException(404, f"Could not find '{text}'. Try a street name with the city.")
            return c.lat, c.lon, c.name
        with _geo_lock:  # Nominatim policy: at most one request per second
            wait = 1.05 - (time.time() - _last_geo[0])
            if wait > 0:
                time.sleep(wait)
            _last_geo[0] = time.time()
            try:
                r = httpx.get("https://nominatim.openstreetmap.org/search", timeout=12, headers={"User-Agent": UA},
                              params={"format": "jsonv2", "limit": 1, "countrycodes": "in", "q": text})
                hits = r.json() if r.status_code == 200 else []
            except (httpx.HTTPError, ValueError):
                raise HTTPException(503, "Place search is unavailable right now. Enter coordinates or try again.")
        if not hits:
            s.add(RouteGeocode(q=key, lat=None, lon=None, name=None))
            s.commit()
            raise HTTPException(404, f"Could not find '{text}'. Try a street name with the city.")
        h = hits[0]
        s.add(RouteGeocode(q=key, lat=float(h["lat"]), lon=float(h["lon"]), name=h.get("display_name", "")[:250]))
        s.commit()
        return float(h["lat"]), float(h["lon"]), (h.get("display_name") or text)[:120]
    finally:
        s.close()


def _to_xy(lat, lon, lat0, lon0):
    return (np.asarray(lon) - lon0) * math.cos(math.radians(lat0)) * 111320.0, (np.asarray(lat) - lat0) * 110540.0


def _dist_to_polyline(px, py, xs, ys):
    """Distance in metres from point (px, py) to the polyline xs, ys (vectorised over segments)."""
    ax, ay, bx, by = xs[:-1], ys[:-1], xs[1:], ys[1:]
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    t = np.where(L2 > 0, ((px - ax) * dx + (py - ay) * dy) / np.where(L2 > 0, L2, 1), 0.0)
    t = np.clip(t, 0, 1)
    cx, cy = ax + t * dx, ay + t * dy
    return float(np.sqrt((px - cx) ** 2 + (py - cy) ** 2).min())


def _osrm_routes(o, d, via=None, alternatives=True):
    pts = [o] + ([via] if via else []) + [d]
    path = ";".join(f"{p[1]},{p[0]}" for p in pts)
    url = f"{OSRM_URL}/route/v1/driving/{path}"
    try:
        r = httpx.get(url, timeout=25, headers={"User-Agent": UA},
                      params={"alternatives": "3" if alternatives and not via else "false", "overview": "full",
                              "geometries": "geojson", "steps": "true"})
        j = r.json()
    except (httpx.HTTPError, ValueError):
        if via:
            return []
        raise HTTPException(503, "The route service is busy. Try again in a moment.")
    if j.get("code") != "Ok" or not j.get("routes"):
        if via:
            return []
        raise HTTPException(404, "No drivable route was found between these places.")
    return j["routes"]


def _instruction(st):
    m = st.get("maneuver", {})
    t, mod, name = m.get("type", ""), m.get("modifier", ""), st.get("name") or ""
    on = f" onto {name}" if name else ""
    if t == "depart":
        return f"Head {mod or 'out'}{(' on ' + name) if name else ''}".replace("Head out", "Start")
    if t == "arrive":
        return "You have arrived at your destination"
    if t == "roundabout" or t == "rotary":
        return f"At the roundabout take exit {m.get('exit', '')}{on}".strip()
    if t in ("turn", "end of road", "fork", "on ramp", "off ramp", "merge", "new name", "continue") or mod:
        verb = {"left": "Turn left", "right": "Turn right", "slight left": "Bear left", "slight right": "Bear right",
                "sharp left": "Sharp left", "sharp right": "Sharp right", "straight": "Continue straight",
                "uturn": "Make a U-turn"}.get(mod, "Continue")
        return verb + on
    return "Continue" + on


def _steps(r):
    out = []
    for leg in r.get("legs", []):
        for st in leg.get("steps", []):
            loc = st.get("maneuver", {}).get("location")
            out.append({"text": _instruction(st), "distance_m": round(st.get("distance", 0)),
                        "lat": loc[1] if loc else None, "lon": loc[0] if loc else None})
    return out


def plan(o, d):
    routes = _osrm_routes(o, d)
    s = SessionLocal()
    try:
        defects = [x for x in s.query(Defect).filter(Defect.status == "active", Defect.lat != None).all()  # noqa: E711
                   if x.class_name not in IGNORED]
    finally:
        s.close()
    lat0, lon0 = (o[0] + d[0]) / 2, (o[1] + d[1]) / 2
    dxy = [(x, *_to_xy(x.lat, x.lon, lat0, lon0)) for x in defects]

    def score(r, i, detour=False):
        coords = r["geometry"]["coordinates"]  # [lon, lat]
        lons, lats = [c[0] for c in coords], [c[1] for c in coords]
        xs, ys = _to_xy(lats, lons, lat0, lon0)
        minx, maxx, miny, maxy = xs.min() - CORRIDOR_M, xs.max() + CORRIDOR_M, ys.min() - CORRIDOR_M, ys.max() + CORRIDOR_M
        hits = []
        for x, px, py in dxy:
            if not (minx <= px <= maxx and miny <= py <= maxy):
                continue
            dist = _dist_to_polyline(float(px), float(py), xs, ys)
            if dist <= CORRIDOR_M:
                w = CLASS_W.get(x.class_name, 0.5)
                hits.append({"uid": x.uid, "number": x.id, "class": x.class_name, "severity": x.severity,
                             "risk": round(float(x.risk_score or 0), 1), "lat": x.lat, "lon": x.lon,
                             "off_route_m": round(dist, 1),
                             "penalty_min": round(PENALTY_MIN_AT_FULL_RISK * (x.risk_score or 0) / 100.0 * w, 2)})
        hits.sort(key=lambda h: -h["risk"])
        step = max(1, len(coords) // 700)
        geom = [[round(c[1], 5), round(c[0], 5)] for c in coords[::step]] + [[round(coords[-1][1], 5), round(coords[-1][0], 5)]]
        penalty = round(sum(h["penalty_min"] for h in hits), 1)
        return {"index": i, "distance_km": round(r["distance"] / 1000, 2), "duration_min": round(r["duration"] / 60, 1),
                "defects": hits, "defect_count": len(hits), "severe_count": sum(1 for h in hits if h["risk"] >= 70),
                "potholes": sum(1 for h in hits if h["class"] == "pothole"), "detour": detour,
                "penalty_min": penalty, "effective_min": round(r["duration"] / 60 + penalty, 1),
                "damage_per_km": round(len(hits) / max(0.1, r["distance"] / 1000), 2), "geometry": geom, "steps": _steps(r)}

    out = [score(r, i) for i, r in enumerate(routes)]

    # A road with many potholes: look for a detour that steers around the worst cluster (via-point on either side).
    best = min(out, key=lambda r: r["effective_min"])
    if best["defect_count"] >= 3:
        pts = best["defects"]
        centre = max(pts, key=lambda h: sum(1 for q in pts if abs(q["lat"] - h["lat"]) < 0.002 and abs(q["lon"] - h["lon"]) < 0.002))
        vx, vy = (d[1] - o[1]) * math.cos(math.radians(lat0)), d[0] - o[0]
        n = math.hypot(vx, vy) or 1.0
        px, py = -vy / n, vx / n  # unit perpendicular (east, north)
        for sign in (1, -1):
            for off in (600.0, 1200.0):
                via = (centre["lat"] + sign * py * off / 110540.0,
                       centre["lon"] + sign * px * off / (111320.0 * math.cos(math.radians(lat0))))
                for r in _osrm_routes(o, d, via=via)[:1]:
                    if r["distance"] > routes[0]["distance"] * 1.9 + 3000:
                        continue
                    cand = score(r, len(out), detour=True)
                    dup = any(abs(c["distance_km"] - cand["distance_km"]) < 0.15 and abs(c["defect_count"] - cand["defect_count"]) <= 1 for c in out)
                    if not dup and cand["defect_count"] < best["defect_count"]:
                        out.append(cand)
            if len(out) >= 5:
                break
    fastest = min(out, key=lambda r: r["duration_min"])
    smoothest = min(out, key=lambda r: (r["penalty_min"], r["duration_min"]))
    best = min(out, key=lambda r: r["effective_min"])
    for r in out:
        r["labels"] = [n for n, v in (("fastest", fastest), ("smoothest", smoothest), ("recommended", best)) if v is r]
    advice = _advice(out, fastest, best)
    return {"routes": out, "recommended": best["index"], "fastest": fastest["index"], "advice": advice,
            "rules": {"corridor_m": CORRIDOR_M, "penalty_min_at_full_risk": PENALTY_MIN_AT_FULL_RISK,
                      "open_defects_considered": len(defects)}}


def _advice(out, fastest, best):
    if len(out) == 1 or best is fastest:
        if fastest["defect_count"] == 0:
            return "The fastest route has no reported road damage on it."
        return (f"The fastest route is also the best choice. It passes {fastest['defect_count']} reported "
                f"defects ({fastest['severe_count']} serious); drive carefully.")
    saved = fastest["defect_count"] - best["defect_count"]
    extra = round(best["duration_min"] - fastest["duration_min"], 1)
    return (f"Take route {best['index'] + 1}: it avoids {saved} reported road defects "
            f"({max(0, fastest['severe_count'] - best['severe_count'])} serious) and takes "
            f"{extra} min longer than the fastest route.")


def register(app):
    Base.metadata.create_all(engine, tables=[RouteGeocode.__table__])

    @app.get("/api/routeplan")
    def route_plan(origin: str = Query(..., min_length=2), dest: str = Query(..., min_length=2)):
        """Public: compare routes by driving time and by reported road damage along each one."""
        o = geocode(origin)
        d = geocode(dest)
        res = plan((o[0], o[1]), (d[0], d[1]))
        res["origin"] = {"lat": o[0], "lon": o[1], "name": o[2]}
        res["destination"] = {"lat": d[0], "lon": d[1], "name": d[2]}
        return res

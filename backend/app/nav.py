"""Navigation engine: place search, pothole-aware routing and turn-by-turn data.

Why this replaced the old planner
  The old planner used the free OSRM demo (car only, no way to avoid an area, no voice-ready turn text) and Nominatim
  (slow, poor typeahead). Research notes:
    - Valhalla: car, motor scooter (two-wheelers, the vehicles potholes hurt most in India), pedestrian, bicycle; true
      `exclude_polygons` so a route can be forced AROUND a pothole cluster; alternates; maneuvers with spoken phrases;
      Hindi instruction text. Public instance for development, self-hostable with an OSM extract for production.
    - Photon (OSM based): real typeahead with places such as hospitals, shops and bus stops, ~1 s.
  The engine address is RD_VALHALLA_URL (default the public instance). See deploy/valhalla for a self-hosted setup.

Endpoints (public, read only)
  GET  /api/nav/search?q=&lat=&lon=            place suggestions
  GET  /api/nav/reverse?lat=&lon=              coordinate to a readable place name
  POST /api/nav/route {origin, dest, mode, avoid, language}
       mode: car | bike (motor scooter, two wheelers) | walk
       -> routes[] each with geometry, distance_km, duration_min, comfort (damage exposure), defects along the route
          (with distance along the route, for 'pothole ahead' alerts) and maneuvers with spoken text.
       When avoid is true the server also builds routes that steer around severe damage clusters and recommends the
       one with the best time plus comfort penalty.
"""
import math
import os
import time
from typing import Optional

import httpx
import numpy as np
from fastapi import HTTPException, Query
from pydantic import BaseModel

from .db import Defect, SessionLocal
from .routing import CLASS_W, IGNORED, PENALTY_MIN_AT_FULL_RISK, _dist_to_polyline, _to_xy

VALHALLA = os.getenv("RD_VALHALLA_URL", "https://valhalla1.openstreetmap.de").rstrip("/")
PHOTON = os.getenv("RD_PHOTON_URL", "https://photon.komoot.io").rstrip("/")
UA = "DishaAI/1.0 (municipal road monitoring)"
COSTING = {"car": "auto", "bike": "motor_scooter", "walk": "pedestrian"}
# how strongly damage hurts each mode (two wheelers feel it most, pedestrians barely)
MODE_FACTOR = {"car": 1.0, "bike": 1.7, "walk": 0.25}
CORRIDOR_M = float(os.getenv("RD_ROUTE_CORRIDOR_M", "15"))
LANGS = {"en": "en-US", "hi": "hi-IN", "kn": "en-US", "mr": "en-US"}

_cache: dict = {}


# ---------------------------------------------------------------- helpers
def _decode6(shape: str):
    """Valhalla encoded polyline (precision 6) -> [(lat, lon)]."""
    pts, i, lat, lon = [], 0, 0, 0
    while i < len(shape):
        for k in (0, 1):
            res, sh = 0, 0
            while True:
                b = ord(shape[i]) - 63
                i += 1
                res |= (b & 0x1F) << sh
                sh += 5
                if b < 0x20:
                    break
            d = ~(res >> 1) if res & 1 else res >> 1
            if k == 0:
                lat += d
            else:
                lon += d
        pts.append((lat / 1e6, lon / 1e6))
    return pts


def _hav(a, b):
    dx = (b[1] - a[1]) * math.cos(math.radians((a[0] + b[0]) / 2)) * 111320.0
    dy = (b[0] - a[0]) * 110540.0
    return math.hypot(dx, dy)


def _ring(lat, lon, r=28.0, n=8):
    dlat = r / 110540.0
    dlon = r / (111320.0 * math.cos(math.radians(lat)))
    return [[round(lon + dlon * math.cos(2 * math.pi * k / n), 6), round(lat + dlat * math.sin(2 * math.pi * k / n), 6)] for k in range(n)]


def _load_defects(bbox=None):
    s = SessionLocal()
    try:
        q = s.query(Defect).filter(Defect.status == "active", Defect.lat != None, Defect.lon != None)  # noqa: E711
        rows = [d for d in q.all() if d.class_name not in IGNORED]
    finally:
        s.close()
    if bbox:
        a, b, c, d = bbox
        rows = [x for x in rows if a <= x.lat <= c and b <= x.lon <= d]
    return rows


def _valhalla(body, tries=2):
    last = None
    for _ in range(tries):
        try:
            r = httpx.post(f"{VALHALLA}/route", json=body, timeout=40, headers={"User-Agent": UA})
            if r.status_code == 200:
                return r.json()
            last = r.json().get("error", r.text[:120]) if r.headers.get("content-type", "").startswith("application/json") else r.text[:120]
            if r.status_code == 400:
                break
        except httpx.HTTPError as e:
            last = str(e)[:100]
        time.sleep(0.6)
    raise HTTPException(503 if not last or "No path" not in str(last) else 404,
                        "No route could be found between these places." if last and "No path" in str(last) else "The route service is busy. Try again in a moment.")


# ---------------------------------------------------------------- route building
def _trip_to_route(trip, defects, mode, idx, detour=False):
    leg = trip["legs"][0]
    pts = _decode6(leg["shape"])
    lat0, lon0 = pts[len(pts) // 2]
    xs, ys = _to_xy([p[0] for p in pts], [p[1] for p in pts], lat0, lon0)
    cum = [0.0]
    for i in range(1, len(pts)):
        cum.append(cum[-1] + _hav(pts[i - 1], pts[i]))
    minx, maxx, miny, maxy = xs.min() - CORRIDOR_M, xs.max() + CORRIDOR_M, ys.min() - CORRIDOR_M, ys.max() + CORRIDOR_M
    hits = []
    for d in defects:
        dx, dy = _to_xy(d.lat, d.lon, lat0, lon0)
        if not (minx <= dx <= maxx and miny <= dy <= maxy):
            continue
        dist = _dist_to_polyline(float(dx), float(dy), xs, ys)
        if dist > CORRIDOR_M:
            continue
        j = int(np.argmin((xs - dx) ** 2 + (ys - dy) ** 2))
        risk = float(d.risk_score or 0)
        hits.append({"uid": d.uid, "number": d.id, "class": d.class_name, "severity": d.severity, "risk": round(risk, 1),
                     "lat": d.lat, "lon": d.lon, "off_m": round(dist, 1), "along_m": round(cum[j]),
                     "penalty_min": round(PENALTY_MIN_AT_FULL_RISK * risk / 100.0 * CLASS_W.get(d.class_name, 0.5) * MODE_FACTOR[mode], 2)})
    hits.sort(key=lambda h: h["along_m"])
    man = []
    for m in leg["maneuvers"]:
        bi = min(m.get("begin_shape_index", 0), len(pts) - 1)
        man.append({"text": m.get("instruction"), "say": m.get("verbal_pre_transition_instruction") or m.get("instruction"),
                    "say_post": m.get("verbal_post_transition_instruction"), "type": m.get("type"),
                    "street": (m.get("street_names") or [None])[0], "length_m": round(m.get("length", 0) * 1000),
                    "time_s": round(m.get("time", 0)), "at": [pts[bi][0], pts[bi][1]], "at_m": round(cum[bi])})
    step = max(1, len(pts) // 900)
    geom = [[round(p[0], 5), round(p[1], 5)] for p in pts[::step]] + [[round(pts[-1][0], 5), round(pts[-1][1], 5)]]
    dur = trip["summary"]["time"] / 60.0
    penalty = round(sum(h["penalty_min"] for h in hits), 1)
    return {"index": idx, "distance_km": round(trip["summary"]["length"], 2), "duration_min": round(dur, 1),
            "defects": hits, "defect_count": len(hits), "severe_count": sum(1 for h in hits if h["risk"] >= 70),
            "potholes": sum(1 for h in hits if h["class"] == "pothole"), "penalty_min": penalty,
            "effective_min": round(dur + penalty, 1), "comfort": _comfort(len(hits), trip["summary"]["length"], penalty),
            "detour": detour, "geometry": geom, "maneuvers": man}


def _comfort(n, km, penalty):
    """0 to 100, higher is a smoother ride."""
    per_km = n / max(km, 0.3)
    return int(max(0, min(100, round(100 - per_km * 9 - penalty * 1.5))))


def _clusters(hits, cell_m=45.0):
    """Merge nearby severe defects so one exclusion polygon covers a cluster."""
    out, seen = [], set()
    for h in hits:
        key = (round(h["lat"] * 111000 / cell_m), round(h["lon"] * 111000 * math.cos(math.radians(h["lat"])) / cell_m))
        if key in seen:
            continue
        seen.add(key)
        out.append(h)
    return out


def plan(origin, dest, mode="car", avoid=True, language="en", route_at=None):
    mode = mode if mode in COSTING else "car"
    lang = LANGS.get(language, "en-US")
    costing = COSTING[mode]
    locs = [{"lat": origin[0], "lon": origin[1], "type": "break"}, {"lat": dest[0], "lon": dest[1], "type": "break"}]
    base_body = {"locations": locs, "costing": costing, "directions_options": {"language": lang, "units": "km"}}
    data = _valhalla({**base_body, "alternates": 2})
    trips = [data["trip"]] + [a["trip"] for a in data.get("alternates", [])]
    pad = 0.01
    bbox = (min(origin[0], dest[0]) - pad, min(origin[1], dest[1]) - pad, max(origin[0], dest[0]) + pad, max(origin[1], dest[1]) + pad)
    defects = _load_defects(bbox)
    routes = [_trip_to_route(t, defects, mode, i) for i, t in enumerate(trips)]

    if avoid and mode != "walk":
        # steer around severe damage: block the worst clusters on the best route so far and ask the engine again
        for _round in range(2):
            best = min(routes, key=lambda r: r["effective_min"])
            bad = [h for h in best["defects"] if h["risk"] >= 55 and h["class"] in ("pothole", "alligator_crack", "manhole")]
            if len(bad) < 2:
                break
            bad.sort(key=lambda h: -h["risk"])
            polys = [_ring(h["lat"], h["lon"]) for h in _clusters(bad)[:30]]
            try:
                d2 = _valhalla({**base_body, "exclude_polygons": polys})
            except HTTPException:
                break
            r2 = _trip_to_route(d2["trip"], defects, mode, len(routes), detour=True)
            dup = any(abs(r["distance_km"] - r2["distance_km"]) < 0.05 and r["defect_count"] == r2["defect_count"] for r in routes)
            # accept only a real improvement that is not absurdly longer
            if (not dup and r2["defect_count"] < best["defect_count"]
                    and r2["duration_min"] <= best["duration_min"] * 1.7 + 8):
                routes.append(r2)
            else:
                break

    fastest = min(routes, key=lambda r: r["duration_min"])
    smoothest = min(routes, key=lambda r: (r["penalty_min"], r["duration_min"]))
    best = min(routes, key=lambda r: r["effective_min"])
    for r in routes:
        r["labels"] = [n for n, v in (("fastest", fastest), ("smoothest", smoothest), ("recommended", best)) if v is r]
    routes.sort(key=lambda r: (r is not best, r["effective_min"]))
    for i, r in enumerate(routes):
        r["index"] = i
    return {"mode": mode, "routes": routes, "recommended": 0, "fastest": routes.index(fastest), "advice": _advice(routes, fastest, best, mode),
            "engine": "valhalla", "language": lang, "defects_considered": len(defects)}


def _advice(routes, fastest, best, mode):
    who = {"car": "your car", "bike": "your two-wheeler", "walk": "you"}[mode]
    if best is fastest:
        if best["defect_count"] == 0:
            return "The fastest route has no reported road damage."
        return (f"This is also the smoothest route available. It passes {best['defect_count']} reported defects "
                f"({best['severe_count']} serious). Drive carefully.")
    saved = fastest["defect_count"] - best["defect_count"]
    extra = round(best["duration_min"] - fastest["duration_min"], 1)
    return (f"Best for {who}: avoids {saved} reported road defects ({max(0, fastest['severe_count'] - best['severe_count'])} serious) "
            f"and takes {extra} min longer than the fastest route.")


# ---------------------------------------------------------------- places
def _photon(q, lat, lon, limit=8):
    key = ("s", q.lower().strip(), round(lat or 0, 1), round(lon or 0, 1))
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < 600:
        return hit[1]
    params = {"q": q, "limit": limit, "lang": "en"}
    if lat is not None and lon is not None:
        params.update(lat=lat, lon=lon, location_bias_scale=0.4)
    try:
        r = httpx.get(f"{PHOTON}/api/", params=params, timeout=15, headers={"User-Agent": UA})
        feats = r.json().get("features", []) if r.status_code == 200 else []
    except (httpx.HTTPError, ValueError):
        feats = []
    out = []
    for f in feats:
        p, c = f.get("properties", {}), f.get("geometry", {}).get("coordinates")
        if not c or (p.get("countrycode") and p["countrycode"] != "IN"):
            continue
        name = p.get("name") or p.get("street") or ""
        sub = ", ".join(x for x in dict.fromkeys([p.get("street") if p.get("name") else None, p.get("district") or p.get("locality"), p.get("city") or p.get("county"), p.get("state")]) if x)
        out.append({"name": name, "address": sub, "lat": c[1], "lon": c[0], "type": p.get("osm_value") or p.get("type")})
    if out:
        if len(_cache) > 400:
            _cache.clear()
        _cache[key] = (time.time(), out)
    return out


class Pt(BaseModel):
    lat: float
    lon: float


class RouteBody(BaseModel):
    origin: Pt
    dest: Pt
    mode: str = "car"
    avoid: bool = True
    language: str = "en"


def register(app):
    @app.get("/api/nav/search")
    def nav_search(q: str = Query(..., min_length=2, max_length=120), lat: Optional[float] = None, lon: Optional[float] = None):
        return _photon(q, lat, lon)

    @app.get("/api/nav/reverse")
    def nav_reverse(lat: float, lon: float):
        try:
            r = httpx.get(f"{PHOTON}/reverse", params={"lat": lat, "lon": lon, "lang": "en"}, timeout=12, headers={"User-Agent": UA})
            f = (r.json().get("features") or [None])[0]
            if f:
                p = f["properties"]
                name = p.get("name") or p.get("street") or p.get("district") or "Dropped pin"
                sub = ", ".join(x for x in dict.fromkeys([p.get("street"), p.get("district"), p.get("city")]) if x and x != name)
                return {"name": name, "address": sub, "lat": lat, "lon": lon}
        except (httpx.HTTPError, ValueError):
            pass
        return {"name": f"{lat:.5f}, {lon:.5f}", "address": "", "lat": lat, "lon": lon}

    @app.post("/api/nav/route")
    def nav_route(b: RouteBody):
        for p in (b.origin, b.dest):
            if not (-90 <= p.lat <= 90 and -180 <= p.lon <= 180):
                raise HTTPException(400, "Invalid coordinates")
        if _hav((b.origin.lat, b.origin.lon), (b.dest.lat, b.dest.lon)) < 30:
            raise HTTPException(400, "The start and destination are almost the same place.")
        res = plan((b.origin.lat, b.origin.lon), (b.dest.lat, b.dest.lon), b.mode, b.avoid, b.language)
        res["origin"] = b.origin.model_dump()
        res["destination"] = b.dest.model_dump()
        return res

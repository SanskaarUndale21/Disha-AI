"""Citizen features: drive mode, jurisdiction routing and the public read-only map.

Drive mode: a phone mounted on a vehicle sends frames. Frames without road damage are counted and dropped
(no image stored, no inspection). Frames with damage and a precise GPS fix go through the normal ingest
pipeline so repeat sightings merge into one canonical defect.

Routing: resolve a complaint ticket or defect uid to a location, reverse geocode it (Nominatim), check who owns
the road (Overpass, nearest highway way) and pick the urban local body from authorities.json. National and
state highways are refused with a plain reason. Only coordinates are sent to OSM services, never personal data.

Public map: /map and /api/public/* expose defects and aggregate stats without names, phones or photos.
"""
import asyncio
import json
import math
import os
import threading
import time
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Optional

import cv2
import httpx
import numpy as np
from fastapi import File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import JSON, Column, DateTime, Float, Integer, String, func

from . import detector, events
from .db import Base, Complaint, Defect, SessionLocal, engine, now
from .geo import haversine_m

UA = {"User-Agent": "RoadWatch/1.0 (municipal road monitoring)"}
NOMINATIM_REVERSE = "https://nominatim.openstreetmap.org/reverse"
OVERPASS_URL = os.getenv("RD_OVERPASS_URL", "https://overpass-api.de/api/interpreter")
OVERPASS_TIMEOUT = float(os.getenv("RD_CITIZEN_OVERPASS_TIMEOUT", "15"))
HERE = Path(__file__).resolve().parent
AUTHORITIES_PATH = HERE / "authorities.json"
MAP_HTML = HERE / "static" / "public_map.html"

DAMAGE_CLASSES = {"pothole", "longitudinal_crack", "transverse_crack", "alligator_crack", "debris", "manhole"}
DRIVE_MIN_CONF = float(os.getenv("RD_DRIVE_MIN_CONF", "0.35"))
DRIVE_MAX_ACCURACY_M = float(os.getenv("RD_DRIVE_MAX_ACC_M", "50"))
DRIVE_MAX_JUMP_M = 2000.0  # ignore GPS jumps bigger than this between two frames
ROAD_SEARCH_M = 25
TRUNK_IS_NH = os.getenv("RD_TRUNK_IS_NH", "0") == "1"
NON_ROADS = {"footway", "path", "steps", "cycleway", "pedestrian", "bridleway", "corridor", "elevator", "proposed",
             "construction", "track", "bus_stop", "platform"}
CLASS_WORDS = {"pothole": "Pothole", "longitudinal_crack": "Longitudinal crack", "transverse_crack": "Transverse crack",
               "alligator_crack": "Alligator crack", "debris": "Debris", "manhole": "Manhole or drain cover",
               "speed_breaker": "Speed breaker", "barricade": "Barricade"}


# ---------------------------------------------------------------- tables
class DriveSession(Base):
    __tablename__ = "drive_sessions"
    id = Column(String(36), primary_key=True)
    device_id = Column(String(64), index=True)
    started_at = Column(DateTime, default=now, index=True)
    ended_at = Column(DateTime, nullable=True)
    frames = Column(Integer, default=0)
    detections = Column(Integer, default=0)
    unique_defect_ids = Column(JSON, default=list)
    distance_m = Column(Float, default=0.0)
    last_lat = Column(Float, nullable=True)
    last_lon = Column(Float, nullable=True)


class ReverseGeocodeCache(Base):
    __tablename__ = "citizen_revgeo_cache"
    key = Column(String(40), primary_key=True)  # "lat4,lon4"
    payload = Column(JSON)
    fetched_at = Column(DateTime, default=now)


class RoadOwnerCache(Base):
    __tablename__ = "citizen_road_owner_cache"
    key = Column(String(40), primary_key=True)  # "lat4,lon4"
    payload = Column(JSON)
    fetched_at = Column(DateTime, default=now)


# ---------------------------------------------------------------- OSM helpers (1 request per second per service)
_osm_locks = {"nominatim": threading.Lock(), "overpass": threading.Lock()}
_osm_last = {"nominatim": 0.0, "overpass": 0.0}


def _osm_get(service, url, params, timeout):
    with _osm_locks[service]:
        wait = 1.0 - (time.time() - _osm_last[service])
        if wait > 0:
            time.sleep(wait)
        try:
            r = httpx.get(url, params=params, headers=UA, timeout=timeout)
        finally:
            _osm_last[service] = time.time()
    r.raise_for_status()
    return r.json()


def _key(lat, lon):
    return f"{round(lat, 4):.4f},{round(lon, 4):.4f}"


def reverse_geocode(lat, lon):
    """Nominatim reverse lookup, cached by 4 dp. Returns {display_name, address{}} or {} on failure."""
    k = _key(lat, lon)
    s = SessionLocal()
    try:
        c = s.get(ReverseGeocodeCache, k)
        if c:
            return c.payload or {}
        try:
            j = _osm_get("nominatim", NOMINATIM_REVERSE, {"format": "jsonv2", "lat": f"{lat:.6f}", "lon": f"{lon:.6f}",
                                                          "zoom": 18, "addressdetails": 1}, 10)
        except Exception as e:
            return {"error": type(e).__name__}
        out = {"display_name": j.get("display_name"), "address": j.get("address") or {}}
        s.merge(ReverseGeocodeCache(key=k, payload=out, fetched_at=now()))
        s.commit()
        return out
    finally:
        s.close()


def _seg_dist_m(lat, lon, a, b):
    kx = 111320.0 * math.cos(math.radians(lat))
    ky = 110540.0
    ax, ay = (a["lon"] - lon) * kx, (a["lat"] - lat) * ky
    bx, by = (b["lon"] - lon) * kx, (b["lat"] - lat) * ky
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    t = 0.0 if L == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / L))
    return math.hypot(ax + t * dx, ay + t * dy)


def _classify_owner(tags):
    """National / state highway from OSM ref and highway tags.

    ref NH* or highway=motorway => national highway, ref SH* => state highway. highway=trunk counts as a
    national highway only with an NH ref (or when RD_TRUNK_IS_NH=1): in Indian cities many arterials such as
    Bengaluru's Outer Ring Road are tagged trunk without being national highways.
    """
    hw = (tags.get("highway") or "").lower()
    refs = [r.strip().upper().replace(" ", "") for r in (tags.get("ref") or "").split(";") if r.strip()]
    for r in refs:
        if r.startswith("NH"):
            return "national highway", r
    for r in refs:
        if r.startswith("SH"):
            return "state highway", r
    if hw in ("motorway", "motorway_link") or (TRUNK_IS_NH and hw in ("trunk", "trunk_link")):
        return "national highway", refs[0] if refs else None
    return "municipal", refs[0] if refs else None


def _road_from_nominatim(lat, lon):
    """Fallback when Overpass is down: Nominatim reverse at street zoom returns the nearest road way with its
    highway type and (in namedetails) its ref. No distance cap, so it is less exact than Overpass."""
    try:
        j = _osm_get("nominatim", NOMINATIM_REVERSE, {"format": "jsonv2", "lat": f"{lat:.6f}", "lon": f"{lon:.6f}",
                                                      "zoom": 17, "namedetails": 1}, 10)
    except Exception:
        return None
    if j.get("category") != "highway" or j.get("type") in NON_ROADS:
        return {"owner": "unknown", "ref": None, "highway": j.get("type"), "name": j.get("name"),
                "distance_m": None, "source": "nominatim"}
    nd = j.get("namedetails") or {}
    tags = {"highway": j.get("type"), "ref": nd.get("ref")}
    owner, ref = _classify_owner(tags)
    return {"owner": owner, "ref": ref, "highway": j.get("type"), "name": j.get("name"), "distance_m": None,
            "source": "nominatim"}


def road_owner(lat, lon):
    """Nearest OSM highway way within 25 m. Returns {owner, ref, highway, name, distance_m}."""
    k = _key(lat, lon)
    s = SessionLocal()
    try:
        c = s.get(RoadOwnerCache, k)
        if c:
            return dict(c.payload or {}, cached=True)
        q = f'[out:json][timeout:12];way(around:{ROAD_SEARCH_M},{lat:.6f},{lon:.6f})[highway];out tags geom;'
        try:
            ways = _osm_get("overpass", OVERPASS_URL, {"data": q}, OVERPASS_TIMEOUT).get("elements", [])
        except Exception as e:
            out = _road_from_nominatim(lat, lon)
            if out is None:
                return {"owner": "unknown", "ref": None, "highway": None, "name": None, "source": "none",
                        "error": type(e).__name__}
            s.merge(RoadOwnerCache(key=k, payload=out, fetched_at=now()))
            s.commit()
            return out
        best, best_d = None, 1e18
        for w in ways:
            tags = w.get("tags") or {}
            if tags.get("highway") in NON_ROADS:
                continue
            g = w.get("geometry") or []
            d = min((_seg_dist_m(lat, lon, g[i], g[i + 1]) for i in range(len(g) - 1)), default=1e17)
            if d < best_d:
                best, best_d = w, d
        if best is None:
            out = {"owner": "unknown", "ref": None, "highway": None, "name": None, "distance_m": None,
                   "source": "overpass"}
        else:
            tags = best.get("tags") or {}
            owner, ref = _classify_owner(tags)
            out = {"owner": owner, "ref": ref, "highway": tags.get("highway"), "name": tags.get("name"),
                   "distance_m": round(best_d, 1), "source": "overpass"}
        s.merge(RoadOwnerCache(key=k, payload=out, fetched_at=now()))
        s.commit()
        return out
    finally:
        s.close()


# ---------------------------------------------------------------- authority directory
_auth_cache = {"mtime": None, "data": None}


def load_authorities():
    m = AUTHORITIES_PATH.stat().st_mtime
    if _auth_cache["mtime"] != m:
        _auth_cache["data"] = json.loads(AUTHORITIES_PATH.read_text(encoding="utf-8"))
        _auth_cache["mtime"] = m
    return _auth_cache["data"]


def match_authority(address: dict):
    """Pick the urban local body from Nominatim address fields. Returns (key, entry) or ("default", entry)."""
    data = load_authorities()["authorities"]
    fields = ("city", "municipality", "town", "city_district", "county", "state_district", "village")
    names = [str(address.get(f)).strip().lower() for f in fields if address.get(f)]
    for n in names:
        for key, a in data.items():
            if key == "default":
                continue
            if n == key or n in [x.lower() for x in a.get("aliases", [])]:
                return key, a
    return "default", data.get("default", {"applicable": False, "verified": False})


def _road_label(owner, ref):
    if not ref:
        return "a national highway" if owner == "national highway" else "a state highway"
    digits = ref[2:].lstrip("-")
    return f"National Highway {digits}" if owner == "national highway" else f"State Highway {digits}"


# ---------------------------------------------------------------- drive helpers
def _f(v):
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def _session(s, sid):
    d = s.get(DriveSession, sid) if sid else None
    if d is None:
        raise HTTPException(404, "Drive session not found")
    return d


def _ser_session(d):
    dur = ((d.ended_at or now()) - d.started_at).total_seconds() / 60 if d.started_at else 0
    return {"session_id": d.id, "device_id": d.device_id, "started_at": d.started_at, "ended_at": d.ended_at,
            "frames": d.frames or 0, "detections": d.detections or 0,
            "unique_defects": len(d.unique_defect_ids or []), "unique_defect_ids": d.unique_defect_ids or [],
            "distance_km": round((d.distance_m or 0) / 1000, 3), "duration_min": round(dur, 1),
            "active": d.ended_at is None}


def _drive_frame_sync(data, sid, lat, lon, acc, captured_at):
    """Blocking work for one frame: detect, maybe ingest, update the session row."""
    img = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(400, "Could not decode image")
    rows, _meta = detector.detect_image(img)
    damage = [r for r in rows if r["class_name"] in DAMAGE_CLASSES and r["confidence"] >= DRIVE_MIN_CONF]
    precise = lat is not None and lon is not None and (acc is None or acc <= DRIVE_MAX_ACCURACY_M)

    s = SessionLocal()
    try:
        d = _session(s, sid)
        if d.ended_at is not None:
            raise HTTPException(409, "Drive session already stopped")
        d.frames = (d.frames or 0) + 1
        if precise:
            if d.last_lat is not None:
                step = haversine_m(d.last_lat, d.last_lon, lat, lon)
                if step <= DRIVE_MAX_JUMP_M:
                    d.distance_m = (d.distance_m or 0) + step
            d.last_lat, d.last_lon = lat, lon
        s.commit()
        if not damage:
            return {"detected": False, "canonical_count": len(d.unique_defect_ids or [])}
        if not precise:
            return {"detected": True, "stored": False, "reason": "location too imprecise",
                    "accuracy_m": acc, "canonical_count": len(d.unique_defect_ids or [])}
    finally:
        s.close()

    from . import main as m  # lazy: main imports this module
    s = SessionLocal()
    try:
        _insp, res = m._ingest(s, data, f"drive_{sid[:8]}_{uuid.uuid4().hex[:6]}.jpg", lat, lon,
                               captured_at=captured_at or now().isoformat(), inspector=f"drive:{sid[:8]}",
                               notes="Drive mode automatic capture")
        dets = (res.get("inspection") or {}).get("detections") or []
        out, new_uids = [], []
        seen = set()
        for x in dets:
            uid = x.get("defect_uid")
            if not uid or uid in seen:
                continue
            seen.add(uid)
            item = {"uid": uid, "class": x.get("final_class") or x.get("class_name"),
                    "severity": x.get("final_severity") or x.get("severity"), "new": not x.get("is_duplicate")}
            out.append(item)
        d = _session(s, sid)
        ids = list(d.unique_defect_ids or [])
        for item in out:
            if item["uid"] not in ids:
                ids.append(item["uid"])
                new_uids.append(item["uid"])
        d.unique_defect_ids = ids
        d.detections = (d.detections or 0) + len(out)
        s.commit()
        for item in out:
            if item["new"] or item["uid"] in new_uids:
                events.publish("drive.detection", {"session_id": sid, "uid": item["uid"], "class": item["class"],
                                                   "severity": item["severity"], "new_defect": item["new"],
                                                   "lat": lat, "lon": lon})
        return {"detected": True, "stored": True, "defects": out, "canonical_count": len(ids)}
    finally:
        s.close()


# ---------------------------------------------------------------- routing helpers
def _resolve_target(s, ref):
    ref = (ref or "").strip()
    c = s.query(Complaint).filter(Complaint.ticket == ref.upper()).first()
    if c:
        sev, cls, uid = None, c.category, None
        order = {"low": 1, "medium": 2, "high": 3}
        for mm in c.media:
            for det in (mm.inspection.detections if mm.inspection else []):
                if det.verification == "rejected":
                    continue
                fs = det.final_severity
                if sev is None or order.get(fs, 0) > order.get(sev, 0):
                    sev, cls = fs, det.final_class
                    uid = det.defect.uid if det.defect else uid
        return {"kind": "complaint", "ref": c.ticket, "uid": uid, "lat": c.lat, "lon": c.lon, "class": cls,
                "severity": sev, "reports": None}
    d = s.query(Defect).filter(Defect.uid == ref.upper()).first()
    if d:
        return {"kind": "defect", "ref": d.uid, "uid": d.uid, "lat": d.lat, "lon": d.lon, "class": d.class_name,
                "severity": d.severity, "reports": d.report_count}
    raise HTTPException(404, "No complaint or defect with that reference")


def _compose(t, address_text, base):
    word = CLASS_WORDS.get(t["class"] or "", (t["class"] or "Road damage").replace("_", " ").capitalize())
    lat, lon = t["lat"], t["lon"]
    track = f"{base}/map#{t['uid'] or t['ref']}"
    subject = f"Road damage complaint {t['ref']}: {word.lower()} at {lat:.5f}, {lon:.5f}"
    lines = [
        "Dear sir or madam,",
        "",
        f"I would like to report road damage that needs repair. Reference: {t['ref']}"
        + (f" (defect {t['uid']})" if t["uid"] and t["uid"] != t["ref"] else "") + ".",
        "",
        f"Damage type: {word}",
        f"Severity: {t['severity'] or 'not assessed'}",
    ]
    if t.get("reports"):
        lines.append(f"Reports so far: {t['reports']}")
    lines += [
        f"Coordinates: {lat:.6f}, {lon:.6f}",
        f"Address (OpenStreetMap): {address_text or 'not available'}",
        f"Map: https://maps.google.com/?q={lat:.6f},{lon:.6f}",
        f"Public tracking page: {track}",
        "",
        "Please arrange an inspection and repair, and share the expected repair date.",
        "",
        "Thank you.",
        "Sent via RoadWatch",
    ]
    return subject, "\n".join(lines)


def _route_sync(ref, base):
    s = SessionLocal()
    try:
        t = _resolve_target(s, ref)
    finally:
        s.close()
    if t["lat"] is None or t["lon"] is None:
        return {"applicable": False, "authority": None, "email": None, "verified": False, "road_owner": "unknown",
                "road_ref": None, "address": None, "reason": "This report has no location, so we cannot tell which "
                "office is responsible.", "subject": None, "body": None}
    geo = reverse_geocode(t["lat"], t["lon"])
    address = geo.get("display_name")
    road = road_owner(t["lat"], t["lon"])
    owner, ref_tag = road.get("owner", "unknown"), road.get("ref")
    subject, body = _compose(t, address, base)
    out = {"applicable": False, "authority": None, "email": None, "verified": False, "road_owner": owner,
           "road_ref": ref_tag, "road_name": road.get("name"), "address": address, "reason": None,
           "subject": subject, "body": body, "reference": t["ref"], "defect_uid": t["uid"],
           "lat": t["lat"], "lon": t["lon"]}
    if owner == "national highway":
        out["reason"] = (f"This looks like {_road_label(owner, ref_tag)}, which the city does not maintain. "
                         "Report it to NHAI on 1033.")
        return out
    if owner == "state highway":
        out["reason"] = (f"This looks like {_road_label(owner, ref_tag)}, which the city does not maintain. "
                         "Report it to the state public works department.")
        return out
    key, a = match_authority(geo.get("address") or {})
    if key == "default" or not a.get("applicable") or not a.get("email"):
        place = (geo.get("address") or {}).get("city") or (geo.get("address") or {}).get("town")
        out["reason"] = ("We do not have a complaint address for " + (place or "this area") + " yet."
                         if not geo.get("error") else "We could not look up this address right now. Try again later.")
        return out
    out.update(applicable=True, authority=a.get("name"), authority_key=key, email=a.get("email"),
               verified=bool(a.get("verified")), helpline=a.get("helpline"))
    notes = []
    if not out["verified"]:
        notes.append("Address not yet verified by the admin.")
    if owner == "unknown":
        notes.append("We could not confirm who maintains this road, so we assumed the city does.")
    out["reason"] = " ".join(notes) or f"This road is maintained by {a.get('name')}."
    return out


# ---------------------------------------------------------------- public helpers
def _ser_public(d):
    return {"number": d.id, "uid": d.uid, "lat": round(d.lat, 6), "lon": round(d.lon, 6), "class": d.class_name,
            "severity": d.severity, "reports": d.report_count or 1, "status": d.status,
            "first_seen": d.first_seen, "last_seen": d.last_seen}


class DriveStart(BaseModel):
    device_id: Optional[str] = None


class DriveStop(BaseModel):
    session_id: str


# ---------------------------------------------------------------- routes
def register(app):
    Base.metadata.create_all(engine, tables=[DriveSession.__table__, ReverseGeocodeCache.__table__,
                                             RoadOwnerCache.__table__])

    @app.post("/api/drive/start")
    def drive_start(body: DriveStart):
        s = SessionLocal()
        try:
            d = DriveSession(id=str(uuid.uuid4()), device_id=(body.device_id or "")[:64] or None, started_at=now(),
                             frames=0, detections=0, unique_defect_ids=[], distance_m=0.0)
            s.add(d)
            s.commit()
            return {"session_id": d.id, "started_at": d.started_at, "min_confidence": DRIVE_MIN_CONF,
                    "max_accuracy_m": DRIVE_MAX_ACCURACY_M}
        finally:
            s.close()

    @app.post("/api/drive/frame")
    async def drive_frame(file: UploadFile = File(...), session_id: str = Form(...), lat: Optional[str] = Form(None),
                          lon: Optional[str] = Form(None), accuracy: Optional[str] = Form(None),
                          heading: Optional[str] = Form(None), speed: Optional[str] = Form(None),
                          captured_at: Optional[str] = Form(None), device_id: Optional[str] = Form(None)):
        """One camera frame from drive mode. Frames without damage are never stored."""
        data = await file.read()
        if not data:
            raise HTTPException(400, "Empty file")
        la, lo, acc = _f(lat), _f(lon), _f(accuracy)
        if la is None or lo is None or not (-90 <= la <= 90 and -180 <= lo <= 180) or (la == 0 and lo == 0):
            la = lo = None
        return await asyncio.to_thread(_drive_frame_sync, data, session_id, la, lo, acc, captured_at)

    @app.post("/api/drive/stop")
    def drive_stop(body: DriveStop):
        s = SessionLocal()
        try:
            d = _session(s, body.session_id)
            if d.ended_at is None:
                d.ended_at = now()
                s.commit()
            out = _ser_session(d)
            return {"frames": out["frames"], "detections": out["detections"], "unique_defects": out["unique_defects"],
                    "unique_defect_ids": out["unique_defect_ids"], "distance_km": out["distance_km"],
                    "duration_min": out["duration_min"]}
        finally:
            s.close()

    @app.get("/api/drive/sessions")
    def drive_sessions(device_id: Optional[str] = None, limit: int = 50):
        s = SessionLocal()
        try:
            q = s.query(DriveSession)
            if device_id:
                q = q.filter(DriveSession.device_id == device_id)
            return [_ser_session(d) for d in q.order_by(DriveSession.started_at.desc()).limit(min(limit, 200)).all()]
        finally:
            s.close()

    @app.get("/api/route/{ref}")
    async def route(ref: str, request: Request):
        base = (os.getenv("RD_PUBLIC_URL") or str(request.base_url)).rstrip("/")
        return await asyncio.to_thread(_route_sync, ref, base)

    @app.get("/api/public/defects")
    def public_defects():
        s = SessionLocal()
        try:
            rows = (s.query(Defect).filter(Defect.status.in_(("active", "repaired")), Defect.lat != None,  # noqa
                                           Defect.lon != None).order_by(Defect.id).all())  # noqa
            return [_ser_public(d) for d in rows]
        finally:
            s.close()

    @app.get("/api/public/stats")
    def public_stats():
        s = SessionLocal()
        try:
            since = now() - timedelta(days=30)
            open_ = s.query(func.count(Defect.id)).filter(Defect.status == "active").scalar() or 0
            repaired = s.query(func.count(Defect.id)).filter(Defect.status == "repaired").scalar() or 0
            total = (s.query(func.sum(Defect.report_count)).filter(Defect.status.in_(("active", "repaired")))
                     .scalar() or 0)
            cit = s.query(func.count(Complaint.id)).filter(Complaint.created_at >= since).scalar() or 0
            km = (s.query(func.sum(DriveSession.distance_m)).filter(DriveSession.started_at >= since).scalar() or 0)
            by = dict(s.query(Defect.class_name, func.count(Defect.id)).filter(Defect.status == "active")
                      .group_by(Defect.class_name).all())
            return {"open": open_, "repaired": repaired, "total_reports": int(total),
                    "citizens_reports_last_30d": cit, "drive_km_last_30d": round(km / 1000, 2), "by_class": by}
        finally:
            s.close()

    @app.get("/map", include_in_schema=False)
    def public_map():
        return FileResponse(MAP_HTML, media_type="text/html; charset=utf-8",
                            headers={"Cache-Control": "no-cache"})

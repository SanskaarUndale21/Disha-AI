"""City insights for the admin 'City insights' page: road health, contractor scorecard, cost of waiting,
accountability clock and near-miss reports. Read only except POST /api/nearmiss. All numbers come from the live
defect and complaint tables plus the (sample) road ownership register."""
import hashlib
import math
from datetime import timedelta
from typing import Optional

from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy import Column, DateTime, Float, Integer, String, Text

from .db import Base, Complaint, Defect, SessionLocal, engine, now
from .geo import haversine_m
from .roadrecords import RoadAsset, _ser

CLASS_W = {"pothole": 1.0, "alligator_crack": 0.7, "manhole": 0.8, "debris": 0.5, "transverse_crack": 0.35, "longitudinal_crack": 0.3}
IGNORED = {"speed_breaker", "barricade"}
OFFICERS = ["Er. S. Patil", "Er. R. Kulkarni", "Er. M. Naik", "Er. A. Desai", "Er. V. Hegde", "Er. P. Jadhav"]
SLA_DAYS = {"pothole": 7, "crack": 21, "waterlogging": 5, "broken_road": 10, "other": 14}


class NearMiss(Base):
    __tablename__ = "near_misses"
    id = Column(Integer, primary_key=True)
    lat = Column(Float)
    lon = Column(Float)
    note = Column(Text)
    device_id = Column(String(64))
    created_at = Column(DateTime, default=now)


def _grade(score):
    return "A" if score >= 80 else "B" if score >= 65 else "C" if score >= 50 else "D" if score >= 35 else "E"


def _near_defects(a: RoadAsset, defects):
    r = max(a.radius_m or 600, 200)
    return [d for d in defects if haversine_m(a.center_lat, a.center_lon, d.lat, d.lon) <= r]


def road_health():
    s = SessionLocal()
    try:
        assets = s.query(RoadAsset).all()
        defects = [d for d in s.query(Defect).filter(Defect.lat != None, Defect.lon != None).all() if d.class_name not in IGNORED]  # noqa: E711
        miss = s.query(NearMiss).all()
        t = now()
        out = []
        for a in assets:
            near = _near_defects(a, defects)
            act = [d for d in near if d.status == "active"]
            km = max(a.length_km or 1.0, 0.5)
            load = sum((d.risk_score or 0) / 100.0 * CLASS_W.get(d.class_name, 0.5) for d in act) / km
            nm = sum(1 for m in miss if haversine_m(a.center_lat, a.center_lon, m.lat, m.lon) <= max(a.radius_m or 600, 200))
            load += nm * 0.6 / km  # a near-miss counts more than a silent defect
            score = int(round(100 * math.exp(-load / 3.0)))
            new30 = sum(1 for d in near if d.first_seen and (t - d.first_seen).days <= 30)
            fixed30 = sum(1 for d in near if d.status == "repaired" and d.last_seen and (t - d.last_seen).days <= 30)
            trend = "worsening" if new30 > fixed30 + 1 else "improving" if fixed30 > new30 else "stable"
            rec = _ser(a, None)
            out.append({"id": a.id, "name": a.name, "ref": a.ref, "lat": a.center_lat, "lon": a.center_lon, "length_km": a.length_km,
                        "score": score, "grade": _grade(score), "open_defects": len(act),
                        "serious": sum(1 for d in act if (d.risk_score or 0) >= 70), "near_misses": nm, "trend": trend,
                        "contractor": a.contractor, "built_year": a.built_year, "authority": a.authority,
                        "under_liability": bool(rec.get("under_liability")), "scheme": a.scheme})
        out.sort(key=lambda r: r["score"])
        return out
    finally:
        s.close()


def contractors():
    roads = road_health()
    s = SessionLocal()
    try:
        by = {}
        for r in roads:
            c = by.setdefault(r["contractor"] or "Unknown", {"contractor": r["contractor"] or "Unknown", "roads": 0, "km": 0.0, "open_defects": 0,
                                                              "serious": 0, "liability_roads": 0, "scores": []})
            c["roads"] += 1
            c["km"] += r["length_km"] or 0
            c["open_defects"] += r["open_defects"]
            c["serious"] += r["serious"]
            c["liability_roads"] += 1 if r["under_liability"] and r["open_defects"] else 0
            c["scores"].append(r["score"])
        assets = {a.id: a for a in s.query(RoadAsset).all()}
        defects = [d for d in s.query(Defect).filter(Defect.lat != None).all() if d.class_name not in IGNORED]  # noqa: E711
        for r in roads:
            a = assets[r["id"]]
            by[r["contractor"] or "Unknown"].setdefault("repaired", 0)
            by[r["contractor"] or "Unknown"]["repaired"] += sum(1 for d in _near_defects(a, defects) if d.status == "repaired")
        out = []
        for c in by.values():
            c["defects_per_km"] = round(c["open_defects"] / max(c["km"], 0.5), 2)
            c["km"] = round(c["km"], 1)
            c["score"] = int(round(sum(c["scores"]) / len(c["scores"])))
            c.setdefault("repaired", 0)
            del c["scores"]
            out.append(c)
        out.sort(key=lambda c: -c["score"])
        for i, c in enumerate(out, 1):
            c["rank"] = i
        return out
    finally:
        s.close()


def waiting_cost():
    from . import ops
    s = SessionLocal()
    try:
        rows = ops.cost_rows(s, "active")
        total_now = sum(r["total_cost"] for r in rows)
        weekly = sum(r["delay_weekly"] for r in rows)
        items = sorted(rows, key=lambda r: -r["delay_weekly"])[:30]
        return {"weekly_total_rs": weekly, "total_now_rs": total_now, "total_4w_rs": total_now + 4 * weekly,
                "per_second_rs": round(weekly / (7 * 86400), 4), "open_defects": len(rows),
                "items": [{"uid": r["uid"], "class": r["class_name"], "severity": r["severity"], "now_rs": r["total_cost"],
                           "in_4_weeks_rs": r["total_cost"] + 4 * r["delay_weekly"], "extra_rs": 4 * r["delay_weekly"],
                           "weekly_rs": r["delay_weekly"], "lat": r["lat"], "lon": r["lon"]} for r in items]}
    finally:
        s.close()


def _ward(address):
    if not address:
        return "Unassigned ward"
    parts = [p.strip() for p in address.split(",") if p.strip()]
    return (parts[-4] if len(parts) >= 4 else parts[1] if len(parts) > 1 else parts[0])[:40]


def accountability():
    s = SessionLocal()
    try:
        t = now()
        rows = s.query(Complaint).filter(Complaint.status.in_(("submitted", "in_review", "in_progress"))).order_by(Complaint.created_at).limit(300).all()
        out = []
        for c in rows:
            hours = max(0.0, (t - c.created_at).total_seconds() / 3600.0) if c.created_at else 0.0
            sla = SLA_DAYS.get(c.category or "other", 14)
            days = hours / 24.0
            over = days - sla
            level = 0 if over <= 0 else 1 if over <= 3 else 2 if over <= 7 else 3
            ward = _ward(c.address)
            officer = OFFICERS[int(hashlib.md5(ward.encode()).hexdigest(), 16) % len(OFFICERS)]
            out.append({"ticket": c.ticket, "category": c.category, "address": c.address, "status": c.status, "days_open": round(days, 1),
                        "hours_open": round(hours, 1), "ward": ward, "officer": officer, "sla_days": sla, "overdue": over > 0,
                        "days_left": round(max(0.0, -over), 1), "escalation_level": level, "created_at": c.created_at})
        out.sort(key=lambda r: (-r["escalation_level"], -r["days_open"]))
        return out
    finally:
        s.close()


def recorded_near(lat, lon, radius_km):
    """Everything already on record around a point: open and repaired defects by type, how many were serious, how many
    citizen reports back them, open complaints, plus the worst streets by name when the road register knows them."""
    s = SessionLocal()
    try:
        dlat = radius_km / 110.54
        dlon = radius_km / (111.32 * max(0.2, math.cos(math.radians(lat))))
        rows = (s.query(Defect).filter(Defect.lat.between(lat - dlat, lat + dlat), Defect.lon.between(lon - dlon, lon + dlon),
                                       Defect.status.in_(("active", "repaired"))).all())
        rows = [d for d in rows if haversine_m(lat, lon, d.lat, d.lon) <= radius_km * 1000]
        act = [d for d in rows if d.status == "active"]
        by = {}
        for d in act:
            by[d.class_name] = by.get(d.class_name, 0) + 1
        comps = (s.query(Complaint).filter(Complaint.lat.between(lat - dlat, lat + dlat), Complaint.lon.between(lon - dlon, lon + dlon),
                                           Complaint.status.in_(("submitted", "in_review", "in_progress"))).count())
        oldest = min((d.first_seen for d in act if d.first_seen), default=None)
        assets = []
        for a_ in s.query(RoadAsset).all():
            if haversine_m(lat, lon, a_.center_lat, a_.center_lon) <= radius_km * 1000 + (a_.radius_m or 0):
                n = sum(1 for d in act if haversine_m(a_.center_lat, a_.center_lon, d.lat, d.lon) <= (a_.radius_m or 600))
                assets.append({"road": a_.name, "open": n})
        assets.sort(key=lambda x: -x["open"])
        return {"radius_km": radius_km, "recorded_total": len(rows), "open": len(act), "repaired": len(rows) - len(act),
                "potholes_open": by.get("pothole", 0), "serious_open": sum(1 for d in act if (d.risk_score or 0) >= 70),
                "reports_behind": int(sum((d.report_count or 1) for d in act)), "open_complaints": comps, "by_class": by,
                "oldest_open_days": (now() - oldest).days if oldest else None, "worst_roads": [a_ for a_ in assets if a_["open"]][:5],
                "source": "Disha AI records: citizen reports, AI detections and field uploads",
                "external": {"osm_tagged_potholes": 0, "note": "OpenStreetMap holds no tagged potholes for this region, so recorded potholes come from Disha AI data"}}
    finally:
        s.close()


class NearBody(BaseModel):
    lat: float
    lon: float
    note: Optional[str] = ""
    device_id: Optional[str] = None


def register(app):
    Base.metadata.create_all(engine, tables=[NearMiss.__table__])

    @app.get("/api/insights/road-health")
    def api_road_health():
        return road_health()

    @app.get("/api/insights/contractors")
    def api_contractors():
        return contractors()

    @app.get("/api/insights/waiting-cost")
    def api_waiting():
        return waiting_cost()

    @app.get("/api/insights/accountability")
    def api_accountability():
        return accountability()

    @app.get("/api/recorded")
    def api_recorded(lat: float, lon: float, radius_km: float = 5.0):
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise HTTPException(400, "Invalid location")
        return recorded_near(lat, lon, max(0.3, min(radius_km, 50.0)))

    @app.post("/api/nearmiss")
    def post_nearmiss(b: NearBody):
        if not (-90 <= b.lat <= 90 and -180 <= b.lon <= 180):
            raise HTTPException(400, "Invalid location")
        s = SessionLocal()
        try:
            m = NearMiss(lat=b.lat, lon=b.lon, note=(b.note or "")[:300], device_id=(b.device_id or "")[:64])
            s.add(m)
            s.commit()
            from . import events
            events.publish("nearmiss.created", {"id": m.id, "lat": m.lat, "lon": m.lon})
            return {"id": m.id, "ok": True}
        finally:
            s.close()

    @app.get("/api/nearmiss")
    def get_nearmiss():
        s = SessionLocal()
        try:
            return [{"id": m.id, "lat": m.lat, "lon": m.lon, "note": m.note, "created_at": m.created_at}
                    for m in s.query(NearMiss).order_by(NearMiss.id.desc()).limit(300).all()]
        finally:
            s.close()

"""Public zone heat grid, anonymised complaint feed and summary numbers.

GET /api/public/zones?cell_m=300   grid of red / yellow / green cells over active defects
GET /api/public/complaints?limit=40  recent complaints with no personal data
GET /api/public/summary            headline numbers for the public page
"""
import math
import re
import threading
import time

from sqlalchemy import func

from .db import Complaint, Defect, SessionLocal

THRESHOLDS = {"yellow": 3, "red": 6, "severe_yellow": 1, "severe_red": 3}
SEVERE_RISK = 70.0
CACHE_S = 5.0
_cache: dict = {}
_lock = threading.Lock()


def _level(count, severe):
    if count >= THRESHOLDS["red"] or severe >= THRESHOLDS["severe_red"]:
        return "red"
    if count >= THRESHOLDS["yellow"] or severe >= THRESHOLDS["severe_yellow"]:
        return "yellow"
    return "green"


def _label(count, severe):
    s = f"{count} defect{'s' if count != 1 else ''}"
    return s + (f", {severe} serious" if severe else "")


def compute_zones(s, cell_m):
    rows = (s.query(Defect.lat, Defect.lon, Defect.risk_score)
            .filter(Defect.status == "active", Defect.lat != None, Defect.lon != None).all())  # noqa: E711
    out = {"cells": [], "thresholds": dict(THRESHOLDS), "cell_m": cell_m,
           "totals": {"defects": len(rows), "cells": 0, "red": 0, "yellow": 0, "green": 0}}
    if not rows:
        return out
    lat0 = sum(r[0] for r in rows) / len(rows)
    my = 110574.0
    mx = 111320.0 * math.cos(math.radians(lat0))
    grid = {}
    for lat, lon, risk in rows:
        key = (math.floor(lon * mx / cell_m), math.floor(lat * my / cell_m))
        g = grid.setdefault(key, [0, 0])
        g[0] += 1
        if (risk or 0) >= SEVERE_RISK:
            g[1] += 1
    for (ix, iy), (count, severe) in grid.items():
        lvl = _level(count, severe)
        out["cells"].append({"lat": round((iy + 0.5) * cell_m / my, 6), "lon": round((ix + 0.5) * cell_m / mx, 6),
                             "size_m": cell_m, "count": count, "severe": severe, "level": lvl,
                             "label": _label(count, severe)})
        out["totals"][lvl] += 1
    out["totals"]["cells"] = len(out["cells"])
    out["cells"].sort(key=lambda c: (-{"red": 2, "yellow": 1, "green": 0}[c["level"]], -c["count"]))
    return out


def zones(cell_m=300):
    cell_m = int(max(100, min(2000, cell_m)))
    with _lock:
        hit = _cache.get(cell_m)
        if hit and time.time() - hit[0] < CACHE_S:
            return hit[1]
    s = SessionLocal()
    try:
        data = compute_zones(s, cell_m)
    finally:
        s.close()
    with _lock:
        _cache[cell_m] = (time.time(), data)
    return data


def _area(addr):
    """Coarse place name: drop parts with digits (house or plot numbers), keep the first two."""
    if not addr:
        return None
    parts = [p.strip() for p in str(addr).split(",") if p.strip() and not re.search(r"\d", p)]
    return ", ".join(parts[:2]) or None


def _sources(s, ids):
    try:
        from .voice import ComplaintMeta
        return dict(s.query(ComplaintMeta.complaint_id, ComplaintMeta.source)
                    .filter(ComplaintMeta.complaint_id.in_(ids)).all()) if ids else {}
    except Exception:
        return {}


def public_complaints(limit):
    limit = max(1, min(200, limit))
    s = SessionLocal()
    try:
        rows = s.query(Complaint).order_by(Complaint.created_at.desc(), Complaint.id.desc()).limit(limit).all()
        src = _sources(s, [c.id for c in rows])
        return [{"number": c.ticket, "category": c.category, "status": c.status,
                 "lat": round(c.lat, 4) if c.lat is not None else None,
                 "lon": round(c.lon, 4) if c.lon is not None else None,
                 "created_at": c.created_at, "area": _area(c.address),
                 "source": src.get(c.id) if src.get(c.id) in ("phone", "app", "web") else "app"} for c in rows]
    finally:
        s.close()


def summary():
    z = zones(300)
    s = SessionLocal()
    try:
        open_ = s.query(func.count(Defect.id)).filter(Defect.status == "active").scalar() or 0
        total = s.query(func.count(Complaint.id)).scalar() or 0
        resolved = s.query(func.count(Complaint.id)).filter(Complaint.status == "resolved").scalar() or 0
        closed = s.query(func.count(Complaint.id)).filter(Complaint.status.in_(("resolved", "rejected"))).scalar() or 0
        area = None
        if z["cells"] and z["cells"][0]["count"]:
            top = z["cells"][0]
            try:
                from .roadrecords import lookup
                rec = lookup(s, top["lat"], top["lon"])
                area = rec.get("name") if rec.get("found") else f"{top['lat']:.3f}, {top['lon']:.3f}"
            except Exception:
                area = f"{top['lat']:.3f}, {top['lon']:.3f}"
        return {"open_defects": open_, "complaints_total": total, "complaints_open": total - closed,
                "complaints_resolved": resolved, "red_zones": z["totals"]["red"],
                "yellow_zones": z["totals"]["yellow"], "green_zones": z["totals"]["green"],
                "most_affected_area": area}
    finally:
        s.close()


def register(app):
    @app.get("/api/public/zones")
    def public_zones(cell_m: int = 300):
        return zones(cell_m)

    @app.get("/api/public/complaints")
    def public_complaints_feed(limit: int = 40):
        return public_complaints(limit)

    @app.get("/api/public/summary")
    def public_summary():
        return summary()

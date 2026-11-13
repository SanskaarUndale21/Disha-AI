"""Road records: who built a road, when, under which scheme, and whether the contractor is still liable.

ALL DATA HERE IS SAMPLE / DUMMY DATA for demonstration. Scheme names are real programmes but the assignments,
contractors (fictional) and costs are invented. Every response carries sample_data and a disclaimer.
Endpoints: GET /api/roads/asset?lat=&lon=, GET /api/roads/assets, GET /api/roads/defect/{defect_id}
"""
from datetime import datetime
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import Boolean, Column, Float, Integer, String

from .db import Base, Defect, SessionLocal, engine
from .geo import haversine_m

DISCLAIMER = "Sample data for demonstration. Not an official government record."
NEAR_FALLBACK_M = 2000.0

SCHEMES = {
    "PMGSY": ("PMGSY", "Pradhan Mantri Gram Sadak Yojana"),
    "SCM": ("Smart Cities Mission", "Smart Cities Mission"),
    "AMRUT": ("AMRUT", "Atal Mission for Rejuvenation and Urban Transformation (AMRUT)"),
    "BHARATMALA": ("Bharatmala Pariyojana", "Bharatmala Pariyojana (NHAI)"),
    "SHDP": ("State Highway Development Project", "State Highway Development Project (Karnataka)"),
    "WHITETOP": ("BBMP White-topping Project", "BBMP White-topping Project"),
    "NAMMA": ("Namma Raste", "Namma Raste"),
}


class RoadAsset(Base):
    __tablename__ = "road_assets"
    id = Column(Integer, primary_key=True)
    name = Column(String(120))
    ref = Column(String(40))
    authority = Column(String(120))
    built_year = Column(Integer)
    contractor = Column(String(120))
    scheme = Column(String(60))
    scheme_full = Column(String(160))
    sanctioned_cost_cr = Column(Float)
    completed_cost_cr = Column(Float)
    length_km = Column(Float)
    lane_count = Column(Integer)
    surface = Column(String(40))
    defect_liability_years = Column(Integer)
    last_resurfaced_year = Column(Integer, nullable=True)
    center_lat = Column(Float)
    center_lon = Column(Float)
    radius_m = Column(Float)
    sample_data = Column(Boolean, default=True)


# name, ref, authority, built, contractor, scheme, sanctioned cr, completed cr, km, lanes, surface, liability yrs,
# last resurfaced, lat, lon, radius m
_SEED = [
    ("MG Road", "BLR-CBD-001", "BBMP", 2019, "Kaveri Roadworks Ltd", "SCM", 42.0, 44.6, 3.2, 4, "Bituminous concrete", 5, 2023, 12.9756, 77.6068, 900),
    ("Church Street", "BLR-CBD-014", "BBMP", 2017, "Sri Venkateshwara Infra Pvt Ltd", "SCM", 9.5, 10.2, 0.9, 2, "Paver blocks", 5, None, 12.9744, 77.6050, 450),
    ("100 Feet Road, Indiranagar", "BLR-E-022", "BBMP", 2021, "Nandi Construction Co", "NAMMA", 18.0, 17.4, 2.1, 4, "Bituminous concrete", 3, None, 12.9716, 77.6411, 800),
    ("80 Feet Road, Koramangala", "BLR-SE-031", "BBMP", 2022, "Malnad Paving Works Pvt Ltd", "WHITETOP", 36.0, 38.9, 2.6, 4, "Concrete (white-topping)", 5, None, 12.9355, 77.6244, 850),
    ("Silk Board Junction and Hosur Service Road", "BLR-SE-040", "BBMP", 2015, "Bhadra Highways Ltd", "AMRUT", 27.0, 31.5, 1.8, 6, "Bituminous concrete", 3, 2020, 12.9171, 77.6233, 700),
    ("Outer Ring Road (Marathahalli to Bellandur)", "BLR-ORR-007", "BBMP", 2014, "Tungabhadra Infra Developers Ltd", "SCM", 120.0, 141.0, 9.5, 6, "Bituminous concrete", 5, 2022, 12.9560, 77.7010, 1500),
    ("Tumkur Road (NH-48)", "NH48-KA-112", "NHAI", 2011, "Deccan Corridor Projects Pvt Ltd", "BHARATMALA", 310.0, 352.0, 14.0, 6, "Bituminous concrete", 5, 2021, 13.0480, 77.5000, 2200),
    ("Hosur Road", "BLR-S-018", "BBMP", 2016, "Sri Venkateshwara Infra Pvt Ltd", "SHDP", 64.0, 66.8, 7.8, 6, "Bituminous concrete", 4, 2022, 12.8800, 77.6400, 1800),
    ("ITPL Main Road, Whitefield", "BLR-E-051", "BBMP", 2020, "Kaveri Roadworks Ltd", "NAMMA", 22.0, 23.1, 3.4, 4, "Bituminous concrete", 3, None, 12.9700, 77.7500, 1400),
    ("Hosur Road, Electronic City Phase 1", "BLR-S-044", "KRDCL", 2018, "Bhadra Highways Ltd", "SHDP", 48.0, 49.3, 4.6, 4, "Bituminous concrete", 4, 2023, 12.8450, 77.6600, 1500),
    ("Yelahanka Main Road", "BLR-N-009", "BBMP", 2013, "Nandi Construction Co", "AMRUT", 14.0, 15.9, 3.8, 2, "Bituminous macadam", 2, 2019, 13.1007, 77.5963, 1500),
    ("11th Main Road, Jayanagar 4th Block", "BLR-S-027", "BBMP", 2023, "Malnad Paving Works Pvt Ltd", "WHITETOP", 11.0, 10.6, 1.2, 2, "Concrete (white-topping)", 5, None, 12.9250, 77.5938, 700),
    ("Pune-Satara Road, Katraj", "PUN-S-003", "PMC", 2016, "Sahyadri Roadbuilders Pvt Ltd", "SCM", 58.0, 63.0, 5.5, 6, "Bituminous concrete", 3, 2021, 18.4575, 73.8678, 1800),
    ("Jangli Maharaj Road, Pune", "PUN-C-012", "PMC", 2020, "Mulshi Infra Ltd", "SCM", 24.0, 25.2, 1.7, 4, "Concrete", 5, None, 18.5196, 73.8420, 1200),
    ("Western Express Highway, Andheri", "MUM-W-005", "MMRDA", 2012, "Konkan Civil Works Ltd", "SHDP", 210.0, 248.0, 6.2, 8, "Bituminous concrete", 5, 2022, 19.1197, 72.8468, 1800),
    ("Linking Road, Bandra", "MUM-W-031", "BMC", 2018, "Arabian Coast Constructions Pvt Ltd", "AMRUT", 31.0, 32.9, 2.3, 4, "Concrete", 5, None, 19.0670, 72.8350, 1100),
    ("Mysuru-Bengaluru Road, city section", "MYS-E-002", "Mysuru City Corporation", 2017, "Cauvery Basin Roadways Ltd", "SHDP", 39.0, 40.2, 4.1, 4, "Bituminous concrete", 4, 2022, 12.2958, 76.6394, 1800),
    ("Gokul Road, Hubballi", "HBL-N-006", "Hubballi-Dharwad Municipal Corporation", 2015, "Krishna Valley Constructions Pvt Ltd", "PMGSY", 7.5, 8.1, 3.0, 2, "Bituminous macadam", 2, 2018, 15.3647, 75.1240, 1800),
]


def _seed():
    s = SessionLocal()
    try:
        if s.query(RoadAsset).count():
            return
        for (name, ref, auth, built, con, sk, sanc, comp, km, lanes, surf, dlp, resurf, lat, lon, rad) in _SEED:
            short, full = SCHEMES[sk]
            s.add(RoadAsset(name=name, ref=ref, authority=auth, built_year=built, contractor=con, scheme=short,
                            scheme_full=full, sanctioned_cost_cr=sanc, completed_cost_cr=comp, length_km=km,
                            lane_count=lanes, surface=surf, defect_liability_years=dlp,
                            last_resurfaced_year=resurf, center_lat=lat, center_lon=lon, radius_m=rad,
                            sample_data=True))
        s.commit()
    finally:
        s.close()


def _ser(a: RoadAsset, distance_m: Optional[float] = None) -> dict:
    year = datetime.now().year
    until = (a.built_year or year) + (a.defect_liability_years or 0)
    under = year <= until
    if under:
        note = f"Built in {a.built_year}. The contractor is responsible for free repairs until {until}."
    else:
        note = f"Defect liability period ended in {until}."
    return {
        "found": True, "id": a.id, "name": a.name, "ref": a.ref, "authority": a.authority,
        "built_year": a.built_year, "age_years": year - (a.built_year or year), "contractor": a.contractor,
        "scheme": a.scheme, "scheme_full": a.scheme_full, "sanctioned_cost_cr": a.sanctioned_cost_cr,
        "completed_cost_cr": a.completed_cost_cr, "length_km": a.length_km, "lane_count": a.lane_count,
        "surface": a.surface, "defect_liability_until": until, "under_liability": under, "liability_note": note,
        "last_resurfaced_year": a.last_resurfaced_year,
        "distance_m": round(distance_m) if distance_m is not None else None,
        "sample_data": True, "disclaimer": DISCLAIMER,
    }


def _none():
    return {"found": False, "sample_data": True, "disclaimer": DISCLAIMER}


def lookup(s, lat, lon) -> dict:
    """Asset record for a point: containing circle (most central first), else nearest within 2 km."""
    if lat is None or lon is None:
        return _none()
    rows = [(haversine_m(lat, lon, a.center_lat, a.center_lon), a) for a in s.query(RoadAsset).all()]
    inside = sorted([(d / max(a.radius_m, 1.0), d, a) for d, a in rows if d <= a.radius_m], key=lambda x: x[0])
    if inside:
        return _ser(inside[0][2], inside[0][1])
    near = sorted([(d, a) for d, a in rows if d <= NEAR_FALLBACK_M], key=lambda x: x[0])
    if near:
        return _ser(near[0][1], near[0][0])
    return _none()


def lookup_point(lat, lon) -> dict:
    """Safe helper for PDFs: never raises."""
    s = SessionLocal()
    try:
        return lookup(s, lat, lon)
    except Exception:
        return _none()
    finally:
        s.close()


def register(app):
    Base.metadata.create_all(engine, tables=[RoadAsset.__table__])
    _seed()

    @app.get("/api/roads/asset")
    def road_asset(lat: float, lon: float):
        return lookup_point(lat, lon)

    @app.get("/api/roads/assets")
    def road_assets():
        s = SessionLocal()
        try:
            out = []
            for a in s.query(RoadAsset).order_by(RoadAsset.id).all():
                d = _ser(a)
                d.update(center_lat=a.center_lat, center_lon=a.center_lon, radius_m=a.radius_m)
                out.append(d)
            return {"assets": out, "sample_data": True, "disclaimer": DISCLAIMER}
        finally:
            s.close()

    @app.get("/api/roads/defect/{defect_id}")
    def road_defect(defect_id: int):
        s = SessionLocal()
        try:
            d = s.get(Defect, defect_id)
            if d is None:
                raise HTTPException(404, "defect not found")
            out = lookup(s, d.lat, d.lon)
            out["defect"] = {"uid": d.uid, "class": d.class_name, "severity": d.severity,
                             "first_seen": d.first_seen}
            return out
        finally:
            s.close()

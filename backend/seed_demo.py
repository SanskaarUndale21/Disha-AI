"""Demo records: drops realistic road defects along real Bengaluru routes so the route planner has data to show.
Demo defects use the uid prefix DM- and can be removed with:  python seed_demo.py --clear
The fastest route of each pair gets many defects, the alternatives get few, so a better route exists to suggest."""
import math
import random
import sys
from datetime import timedelta

import httpx

sys.path.insert(0, ".")
from app.db import Defect, SessionLocal, now  # noqa: E402

PAIRS = [
    ("MG Road", (12.9756, 77.6068), "Koramangala", (12.9352, 77.6245)),
    ("Majestic", (12.9784, 77.5724), "Indiranagar", (12.9784, 77.6408)),
    ("Silk Board", (12.9177, 77.6233), "Marathahalli", (12.9591, 77.6974)),
    ("Hebbal", (13.0358, 77.5970), "MG Road", (12.9756, 77.6068)),
    ("Jayanagar", (12.9250, 77.5938), "Whitefield", (12.9698, 77.7500)),
    ("Banashankari", (12.9255, 77.5468), "Electronic City", (12.8452, 77.6602)),
]
CLASSES = [("pothole", 0.62), ("alligator_crack", 0.12), ("longitudinal_crack", 0.08), ("transverse_crack", 0.06),
           ("manhole", 0.06), ("debris", 0.06)]
SEV = [("Minor", 25, "Low"), ("Moderate", 48, "Medium"), ("Severe", 72, "High"), ("Critical", 90, "High")]


def pick(pairs):
    r, a = random.random(), 0
    for v, w in pairs:
        a += w
        if r <= a:
            return v
    return pairs[0][0]


def along(coords, n):
    """n random points along a [lon, lat] polyline, jittered a few metres off the centre line."""
    pts = []
    for _ in range(n):
        i = random.randrange(len(coords) - 1)
        t = random.random()
        lon = coords[i][0] + (coords[i + 1][0] - coords[i][0]) * t
        lat = coords[i][1] + (coords[i + 1][1] - coords[i][1]) * t
        lat += random.uniform(-5, 5) / 110540
        lon += random.uniform(-5, 5) / (111320 * math.cos(math.radians(lat)))
        pts.append((lat, lon))
    return pts


def main():
    random.seed(7)
    s = SessionLocal()
    if "--clear" in sys.argv:
        n = s.query(Defect).filter(Defect.uid.like("DM-%")).delete(synchronize_session=False)
        s.commit()
        print("removed", n)
        return
    if s.query(Defect).filter(Defect.uid.like("DM-%")).count():
        print("demo records already present (use --clear first)")
        return
    k = 0
    for na, a, nb, b in PAIRS:
        url = f"https://router.project-osrm.org/route/v1/driving/{a[1]},{a[0]};{b[1]},{b[0]}"
        try:
            routes = httpx.get(url, params={"alternatives": "3", "overview": "full", "geometries": "geojson"}, timeout=30).json()["routes"]
        except Exception as e:
            print("skip", na, nb, e)
            continue
        for ri, r in enumerate(routes):
            km = r["distance"] / 1000
            n = int(km * (random.uniform(5, 8) if ri == 0 else random.uniform(0.6, 1.8)))
            for lat, lon in along(r["geometry"]["coordinates"], n):
                k += 1
                cls = pick(CLASSES)
                sev, score, lvl = random.choices(SEV, weights=[3, 4, 3, 1] if ri == 0 else [5, 3, 1, 0.3])[0]
                repaired = random.random() < 0.08
                first = now() - timedelta(days=random.randint(2, 200))
                s.add(Defect(uid=f"DM-{k:04d}", class_name=cls, lat=lat, lon=lon, location_source="demo", road_type="urban",
                             traffic_level=random.choice(["medium", "high"]), severity=sev, severity_score=score,
                             risk_score=score + random.uniform(-6, 6), risk_level=lvl,
                             status="repaired" if repaired else "active", trend="repaired" if repaired else "stable",
                             report_count=random.randint(1, 9), first_seen=first, last_seen=now() - timedelta(days=random.randint(0, 5))))
        print(na, "->", nb, len(routes), "routes")
    s.commit()
    print("seeded", k, "demo defects")


if __name__ == "__main__":
    main()

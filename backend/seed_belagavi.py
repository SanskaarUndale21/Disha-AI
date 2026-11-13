"""Demo records for Belagavi: complaints that read like real citizen filings, each classified (category, damage class,
severity, priority, assigned office), matching road defects on the map, and sample road ownership records.
All demo rows are tagged so they can be removed:  python seed_belagavi.py --clear
(complaints: device_id 'demo-belagavi', defects: uid BG-xxxx, road assets: ref BGM-xxx)"""
import random
import sys
from datetime import timedelta

sys.path.insert(0, ".")
from app.db import Base, Complaint, Defect, SessionLocal, engine, now  # noqa: E402
from app.roadrecords import SCHEMES, RoadAsset  # noqa: E402
from app.voice import ComplaintMeta  # noqa: E402

TAG = "demo-belagavi"
AUTH = "Belagavi City Corporation"
Base.metadata.create_all(engine)

# (area, road, lat, lon)
PLACES = [
    ("Khade Bazar, Shahapur", "Khade Bazar Main Road", 15.8456, 74.5066),
    ("Tilakwadi", "Tilakwadi Railway Gate Road", 15.8383, 74.5051),
    ("Camp", "Congress Road, Camp", 15.8627, 74.5098),
    ("Udyambag", "Udyambag Industrial Road", 15.8152, 74.5201),
    ("Hindwadi", "Hindwadi Main Road", 15.8232, 74.5003),
    ("Sadashiv Nagar", "Sadashiv Nagar 2nd Cross", 15.8745, 74.5162),
    ("Angol", "Angol Road", 15.8262, 74.4902),
    ("Vadgaon", "Vadgaon-Belagavi Road", 15.8231, 74.5198),
    ("Peeranwadi", "Peeranwadi Junction", 15.8846, 74.4812),
    ("Fort Road", "Fort Lake Road", 15.8571, 74.5062),
    ("College Road", "College Road near Lingaraj College", 15.8619, 74.5006),
    ("Club Road", "Club Road", 15.8702, 74.5041),
    ("Khanapur Road", "Khanapur Road near Ganesh Mandir", 15.8624, 74.4893),
    ("Gandhi Nagar", "Gandhi Nagar Circle", 15.8692, 74.4961),
    ("Mahantesh Nagar", "Mahantesh Nagar Main Road", 15.8781, 74.5023),
    ("Ganeshpur", "Ganeshpur Road", 15.8852, 74.5148),
    ("Kakati", "Kakati Cross", 15.8901, 74.4751),
    ("Bogarves", "Bogarves Road", 15.8331, 74.5169),
    ("Hindalga", "Hindalga Gram Panchayat Road", 15.8692, 74.5524),
    ("Chennamma Circle", "Chennamma Circle to Collector Office", 15.8534, 74.5071),
    ("RPD Cross", "RPD Cross to Tilakwadi", 15.8483, 74.5033),
    ("Shivbasava Nagar", "Shivbasava Nagar 5th Cross", 15.8552, 74.4896),
    ("Anagol", "Anagol Main Road", 15.8180, 74.5060),
    ("Nehru Nagar", "Nehru Nagar Circle", 15.8801, 74.5095),
]

# category, damage class, severity, score, risk, priority, text templates
KINDS = [
    ("pothole", "pothole", "Critical", 92, "High", "P1 (fix within 72 hours)", [
        "Huge pothole in the middle of the road near {road}. Two wheelers are skidding, an auto overturned yesterday evening. Please fix urgently.",
        "Deep pothole full of water on {road}, {area}. Cannot see it at night, many bikers have fallen. Needs immediate repair.",
        "Pothole about 2 feet wide and very deep at {road}. School children walk here. Dangerous."]),
    ("pothole", "pothole", "Severe", 74, "High", "P2 (fix within 7 days)", [
        "Many potholes on {road} after the rain. Vehicles slow down suddenly and there is traffic jam in the morning.",
        "Road surface came off near {road}, {area}. Big pothole forming, getting worse every week.",
        "Pothole near the bus stop at {area}. Buses and autos swerve to avoid it."]),
    ("pothole", "pothole", "Moderate", 52, "Medium", "P3 (fix within 15 days)", [
        "Small potholes along {road}. Not very deep but uncomfortable for two wheelers.",
        "Patchwork done last year has come out again at {road}. Few potholes forming."]),
    ("crack", "alligator_crack", "Severe", 70, "High", "P2 (fix within 7 days)", [
        "Road is cracked all over near {road}, looks like a net. Water goes inside and road is breaking.",
        "Alligator type cracks on {road}, {area}. Heavy trucks use this road daily, it is sinking at the edges."]),
    ("crack", "longitudinal_crack", "Moderate", 48, "Medium", "P3 (fix within 15 days)", [
        "Long crack running along {road}. Looks like it is growing. Please inspect before monsoon.",
        "Crack along the edge of the road at {area}, near the drain. Part of the road may collapse."]),
    ("waterlogging", None, "Moderate", 55, "Medium", "P2 (clear within 7 days)", [
        "Water stands on {road} for many days after rain, drain is blocked. Mosquitoes and bad smell.",
        "Whole stretch of {road} gets flooded with a little rain. Drain cleaning is pending since last month."]),
    ("broken_road", "pothole", "Critical", 88, "High", "P1 (fix within 72 hours)", [
        "Road is completely broken near {road}. Only stones are left, cars are getting damaged.",
        "Road dug up for pipe work and not restored at {road}, {area}. Open trench, very risky at night."]),
    ("other", None, "Minor", 30, "Low", "P4 (schedule)", [
        "Manhole cover is missing near {road}. Someone has put a stick as warning. Please fix.",
        "Road marking and speed breaker paint have faded at {area}, accidents near the school."]),
]
STATUS_W = [("submitted", 5), ("in_review", 5), ("in_progress", 6), ("resolved", 7), ("rejected", 1)]
NOTES = {
    "in_review": "Received by the roads wing. Site inspection scheduled.",
    "in_progress": "Work order issued to the ward contractor. Repair to start this week.",
    "resolved": "Repaired and verified by the ward engineer. Closed.",
    "rejected": "Inspection found the road in acceptable condition. Closed without work.",
}
NAMES = ["Basavaraj Patil", "Savita Kulkarni", "Mahesh Jadhav", "Shweta Desai", "Ravi Naik", "Anita Hegde", "Suresh Gouda",
         "Pooja Shinde", "Irfan Mulla", "Kavita Joshi", "Sachin Bhosale", "Rekha Pawar", "Manjunath Kamble", "Nikhil Chavan",
         "Lakshmi Gokak", "Prakash Malagi", "Sunita More", "Vinayak Hosamani", "Farhan Sayyad", "Deepa Revankar"]

# sample road ownership records
ROADS = [
    ("Khanapur Road, Belagavi", "BGM-C-001", 2018, "Malaprabha Constructions Pvt Ltd", "SCM", 36.0, 38.4, 4.6, 4, "Bituminous concrete", 5, None, 15.8624, 74.4893, 1500),
    ("Congress Road, Camp", "BGM-C-004", 2021, "Ghataprabha Infra Ltd", "SCM", 18.0, 18.9, 2.1, 4, "Concrete (white-topping)", 5, None, 15.8627, 74.5098, 1100),
    ("Tilakwadi Main Road", "BGM-S-007", 2015, "Krishna Valley Constructions Pvt Ltd", "AMRUT", 12.5, 13.8, 3.2, 2, "Bituminous macadam", 3, 2020, 15.8383, 74.5051, 1200),
    ("Udyambag Industrial Road", "BGM-I-011", 2012, "Sahyadri Roadbuilders Pvt Ltd", "SHDP", 22.0, 25.6, 5.0, 2, "Bituminous concrete", 4, 2019, 15.8152, 74.5201, 1600),
    ("Belagavi-Pune Highway (NH-48) city stretch", "NH48-BGM-021", 2013, "Deccan Corridor Projects Pvt Ltd", "BHARATMALA", 190.0, 214.0, 9.5, 6, "Bituminous concrete", 5, 2022, 15.8902, 74.5330, 2600),
    ("Fort Lake Road", "BGM-C-015", 2019, "Ghataprabha Infra Ltd", "SCM", 9.0, 9.4, 1.4, 2, "Bituminous concrete", 5, None, 15.8571, 74.5062, 900),
]


def pick(pairs):
    r, a = random.random() * sum(w for _, w in pairs), 0
    for v, w in pairs:
        a += w
        if r <= a:
            return v
    return pairs[0][0]


def clear(s):
    ids = [c.id for c in s.query(Complaint).filter(Complaint.device_id == TAG).all()]
    if ids:
        s.query(ComplaintMeta).filter(ComplaintMeta.complaint_id.in_(ids)).delete(synchronize_session=False)
    n1 = s.query(Complaint).filter(Complaint.device_id == TAG).delete(synchronize_session=False)
    n2 = s.query(Defect).filter(Defect.uid.like("BG-%")).delete(synchronize_session=False)
    n3 = s.query(RoadAsset).filter(RoadAsset.ref.like("BGM-%")).delete(synchronize_session=False)
    s.commit()
    print(f"removed complaints={n1} defects={n2} road records={n3}")


def main():
    random.seed(2026)
    s = SessionLocal()
    if "--clear" in sys.argv:
        clear(s)
        return
    if s.query(Complaint).filter(Complaint.device_id == TAG).count():
        print("Belagavi demo records already present (use --clear first)")
        return
    for (name, ref, built, con, sk, sanc, comp, km, lanes, surf, dlp, resurf, lat, lon, rad) in ROADS:
        short, full = SCHEMES[sk]
        s.add(RoadAsset(name=name, ref=ref, authority=AUTH if not ref.startswith("NH48") else "NHAI", built_year=built, contractor=con,
                        scheme=short, scheme_full=full, sanctioned_cost_cr=sanc, completed_cost_cr=comp, length_km=km,
                        lane_count=lanes, surface=surf, defect_liability_years=dlp, last_resurfaced_year=resurf,
                        center_lat=lat, center_lon=lon, radius_m=rad, sample_data=True))
    nc = nd = 0
    t_now = now()
    for i in range(46):
        area, road, lat, lon = random.choice(PLACES)
        cat, cls, sev, score, risk, prio, texts = random.choice(KINDS)
        lat += random.uniform(-0.0012, 0.0012)
        lon += random.uniform(-0.0012, 0.0012)
        status = pick(STATUS_W)
        if status == "rejected" and sev in ("Critical", "Severe"):
            status = "in_progress"  # serious damage is never closed without work
        created = t_now - timedelta(days=random.randint(0, 48), hours=random.randint(0, 23), minutes=random.randint(0, 59))
        updated = created if status == "submitted" else created + timedelta(days=random.randint(1, 9), hours=random.randint(0, 6))
        if updated > t_now:
            updated = t_now
        src = random.choices(["app", "phone", "web"], weights=[6, 3, 2])[0]
        desc = random.choice(texts).format(road=road, area=area)
        c = Complaint(ticket=f"TMP{i}", category=cat, description=desc, citizen_name=random.choice(NAMES),
                      citizen_phone="9" + "".join(random.choice("0123456789") for _ in range(9)), device_id=TAG, lat=lat, lon=lon,
                      address=f"{road}, {area}, Belagavi, Karnataka", status=status,
                      admin_note=(NOTES.get(status, "") + f" Classified: {cat.replace('_', ' ')}"
                                  + (f" / {cls.replace('_', ' ')}" if cls else "") + f", severity {sev}, priority {prio}. Assigned to {AUTH}, roads wing.").strip(),
                      created_at=created, updated_at=updated)
        s.add(c)
        s.flush()
        c.ticket = f"RW-{c.id:06d}"
        s.add(ComplaintMeta(complaint_id=c.id, source=src, verification="verified" if status != "rejected" else "rejected",
                            location_text=f"{road}, {area}", landmark=area, geocode_source="gps" if src != "phone" else "nominatim",
                            issue_type=(cls or cat).replace("_", " "), urgency="high" if sev in ("Critical", "Severe") else "normal"))
        nc += 1
        if cls:  # a matching damage record on the map, classified by type and severity
            nd += 1
            repaired = status == "resolved"
            s.add(Defect(uid=f"BG-{nd:04d}", class_name=cls, lat=lat, lon=lon, location_source="citizen", road_type="urban",
                         traffic_level=random.choice(["medium", "high"]), severity=sev, severity_score=score,
                         risk_score=0.0 if repaired else score + random.uniform(-5, 5), risk_level="Low" if repaired else risk,
                         status="repaired" if repaired else "active", trend="repaired" if repaired else random.choice(["new", "stable", "worsening"]),
                         report_count=random.randint(1, 6), first_seen=created, last_seen=updated, verified=status in ("in_progress", "resolved")))
    s.commit()
    print(f"added {nc} complaints, {nd} classified defects, {len(ROADS)} road records for Belagavi")


if __name__ == "__main__":
    main()

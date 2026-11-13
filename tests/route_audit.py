import sys, random, time
sys.path.insert(0, '.')
from fastapi.testclient import TestClient
from app.main import app
c = TestClient(app)
random.seed(5)
def pt(box): return (random.uniform(box[0], box[2]), random.uniform(box[1], box[3]))
boxes = {"BLR": (12.90, 77.55, 13.02, 77.70), "BGM": (15.82, 74.46, 15.90, 74.56)}
bad = 0
rows = []
for city, bx in boxes.items():
    for i in range(7):
        o, d = pt(bx), pt(bx)
        for mode in ("car", "bike"):
            r = c.post('/api/nav/route', json={'origin': {'lat': o[0], 'lon': o[1]}, 'dest': {'lat': d[0], 'lon': d[1]}, 'mode': mode})
            if r.status_code != 200:
                rows.append((city, mode, 'ERR', r.status_code)); continue
            j = r.json(); rt = j['routes']; rec = rt[0]
            fewest = min(rt, key=lambda x: x['defect_count'])
            flag = ''
            if rec['defect_count'] > fewest['defect_count']:
                flag = 'REC_NOT_FEWEST'
            if rec['defect_count'] >= 25 and len(rt) > 1 and fewest['defect_count'] < rec['defect_count'] * 0.7:
                flag += ' BIG_GAP'
            rows.append((city, mode, round(rec['distance_km'], 1), round(rec['duration_min']), rec['defect_count'], rec['severe_count'],
                         'fewest', fewest['defect_count'], fewest['duration_min'], len(rt), flag))
for r in rows: print(r)

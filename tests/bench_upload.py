"""Upload every file in samples/ through the real API and report seconds, frames, tracked defects and confidence.
usage: python tests/bench_upload.py [base_url] [quality] [name_filter]"""
import glob
import os
import sys
import time

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
Q = sys.argv[2] if len(sys.argv) > 2 else "2k"
FILT = sys.argv[3] if len(sys.argv) > 3 else ""
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
rows = []
for f in sorted(glob.glob(os.path.join(ROOT, "samples", "**", "*"), recursive=True)):
    n = os.path.basename(f)
    if not n.lower().endswith((".jpg", ".jpeg", ".png", ".mp4", ".mov")) or FILT not in n or n in ("plain_road_test.jpg", "bus_test.jpg"):
        continue
    vid = n.lower().endswith((".mp4", ".mov"))
    t = time.time()
    r = httpx.post(BASE + "/api/inspections", files={"file": (n, open(f, "rb").read())}, data={"quality": Q, "lat": "15.85", "lon": "74.50"}, timeout=600)
    j = r.json()
    if r.status_code != 200:
        print(n, "HTTP", r.status_code, j); continue
    if vid:
        while True:
            st = httpx.get(f"{BASE}/api/jobs/{j['job_id']}", timeout=60).json()
            if st["status"] in ("done", "error"):
                break
            time.sleep(1)
        insp = st.get("inspection") or {}
        if st["status"] == "error":
            print(n, "ERROR", st.get("error")); continue
    else:
        insp = j.get("inspection") or j
    dt = time.time() - t
    dets = [d for d in (insp.get("detections") or []) if d.get("verification") != "rejected"]
    confs = [d.get("confidence") or 0 for d in dets]
    hi = sum(1 for c in confs if c >= 0.40)
    s = insp.get("summary") or {}
    mb = os.path.getsize(f) / 1048576
    print(f"{n[:34]:34} {mb:5.1f}MB  {dt:6.1f}s  frames={insp.get('frames_processed') or 1:4}  tracked={s.get('unique_tracks', len(dets)):3}  dets={len(dets):3}  "
          f"maxconf={max(confs, default=0):.2f}  avgconf={(sum(confs)/len(confs) if confs else 0):.2f}  high>=0.40:{hi}/{len(confs)}  falls={len(s.get('falls', []))}")

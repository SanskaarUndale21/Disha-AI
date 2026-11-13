"""Stress and robustness test for the RoadWatch backend. Run: python tests/stress.py [base_url]
Phases: read load, websocket fan-out, complaint flood, fake-image screening, concurrent image and video analysis,
person-down alarm over websocket, route planner burst, malformed-input fuzzing. Prints PASS/FAIL per phase."""
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path

import httpx
import websockets

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
WS = BASE.replace("http", "ws")
ROOT = Path(__file__).resolve().parents[1]
S = ROOT / "samples"
results = []


def report(name, ok, detail=""):
    results.append((name, ok, detail))
    print(("PASS " if ok else "FAIL ") + name + (" | " + detail if detail else ""), flush=True)


def pct(v, p):
    v = sorted(v)
    return v[min(len(v) - 1, int(len(v) * p))] if v else 0


async def read_load(c):
    paths = ["/api/public/defects", "/api/public/stats", "/api/public/zones", "/api/public/summary", "/api/public/complaints", "/map",
             "/api/health", "/api/defects", "/api/stats"]
    lat, errs = [], 0
    sem = asyncio.Semaphore(60)

    async def one(p):
        nonlocal errs
        async with sem:
            t = time.time()
            try:
                r = await c.get(BASE + p, timeout=60)
                if r.status_code >= 400:
                    errs += 1
            except Exception:
                errs += 1
            lat.append(time.time() - t)

    await asyncio.gather(*[one(paths[i % len(paths)]) for i in range(450)])
    report("read load 450 req @60 concurrent", errs == 0 and pct(lat, 0.95) < 8,
           f"errors={errs} p50={statistics.median(lat):.2f}s p95={pct(lat, 0.95):.2f}s")


async def ws_fanout(c):
    n, got = 120, 0
    stop = asyncio.Event()

    async def client():
        nonlocal got
        try:
            async with websockets.connect(WS + "/ws/events", max_size=None) as ws:
                while not stop.is_set():
                    m = json.loads(await asyncio.wait_for(ws.recv(), 25))
                    if m.get("type") == "map.report":
                        got += 1
                        return
        except Exception:
            return

    tasks = [asyncio.create_task(client()) for _ in range(n)]
    await asyncio.sleep(4)
    r = await c.post(BASE + "/api/complaints", data={"category": "pothole", "description": "stress fan-out test", "lat": "12.97", "lon": "77.59", "device_id": "stress-ws"})
    await asyncio.wait(tasks, timeout=20)
    stop.set()
    report(f"websocket fan-out to {n} clients", r.status_code == 200 and got >= n * 0.95, f"filed={r.status_code} delivered={got}/{n}")


async def complaint_flood(c):
    sem = asyncio.Semaphore(20)
    bad = 0

    async def one(i):
        nonlocal bad
        async with sem:
            r = await c.post(BASE + "/api/complaints", data={"category": "pothole", "description": f"stress complaint {i}", "lat": f"{12.9 + i * 0.0005}", "lon": "77.6", "device_id": f"stress-{i % 7}"}, timeout=60)
            if r.status_code != 200:
                bad += 1

    await asyncio.gather(*[one(i) for i in range(60)])
    report("60 concurrent complaints", bad == 0, f"failed={bad}")


async def screening(c):
    f = S / "plain_road_test.jpg"
    if not f.exists():
        report("fake-image screening", False, "sample missing")
        return
    data = f.read_bytes()

    async def one(i):
        r = await c.post(BASE + "/api/screening/check", files={"file": ("x.jpg", data, "image/jpeg")}, data={"device_id": f"stress-scr-{i % 3}"}, timeout=120)
        return r.json().get("verdict") if r.status_code == 200 else f"http{r.status_code}"

    v = await asyncio.gather(*[one(i) for i in range(12)])
    report("plain-road photo rejected (no fake complaints)", all(x in ("fail", "rate_limited") for x in v), str({k: v.count(k) for k in set(v)}))


async def image_load(c):
    f = S / "pothole_frame.jpg"
    imgs = [p for p in S.glob("*.jpg") if p.name != "plain_road_test.jpg"] or [S / "bus_test.jpg"]
    f = imgs[0]
    data = f.read_bytes()
    sem = asyncio.Semaphore(4)
    bad = 0

    async def one(i):
        nonlocal bad
        async with sem:
            r = await c.post(BASE + "/api/inspections", files={"file": (f.name, data, "image/jpeg")}, data={"lat": "12.95", "lon": f"{77.6 + i * 0.001}"}, timeout=300)
            if r.status_code != 200:
                bad += 1

    t = time.time()
    await asyncio.gather(*[one(i) for i in range(12)])
    report("12 image analyses (4 parallel)", bad == 0, f"failed={bad} total={time.time() - t:.0f}s")


async def video_load(c):
    v = S / "synthetic_pan.mp4"
    data = v.read_bytes()
    jobs = []
    for i in range(3):
        r = await c.post(BASE + "/api/inspections", files={"file": (v.name, data, "video/mp4")}, data={"quality": "2k" if i != 2 else "4k", "classes": "pothole,manhole"}, timeout=120)
        jobs.append(r.json().get("job_id") if r.status_code == 200 else None)
    ok = 0
    for j in jobs:
        if not j:
            continue
        for _ in range(150):
            st = (await c.get(BASE + f"/api/jobs/{j}", timeout=60)).json()
            if st["status"] in ("done", "error"):
                ok += st["status"] == "done"
                break
            await asyncio.sleep(3)
    report("3 concurrent video analyses (2K,2K,4K + class filter)", ok == 3, f"completed={ok}/3")


async def fall_alarm(c):
    v = S / "fall_test.mp4"
    if not v.exists():
        report("person-down alarm on websocket", False, "sample missing")
        return
    got = {}

    async def listen():
        async with websockets.connect(WS + "/ws/events", max_size=None) as ws:
            while True:
                m = json.loads(await ws.recv())
                if m.get("type") == "emergency.fall":
                    got["ev"] = m
                    return

    task = asyncio.create_task(listen())
    await asyncio.sleep(2)
    r = await c.post(BASE + "/api/inspections", files={"file": (v.name, v.read_bytes(), "video/mp4")}, timeout=120)
    try:
        await asyncio.wait_for(task, 120)
    except Exception:
        pass
    report("person-down alarm reaches websocket clients", "ev" in got, f"upload={r.status_code}")


async def route_burst(c):
    async def one(i):
        r = await c.get(BASE + "/api/routeplan", params={"origin": f"12.97{i},77.59", "dest": "12.9352,77.6245"}, timeout=120)
        return r.status_code

    codes = await asyncio.gather(*[one(i) for i in range(8)])
    report("8 concurrent route plans", all(x == 200 for x in codes), str(codes))


async def fuzz(c):
    bad5xx = []
    cases = [
        ("POST", "/api/complaints", dict(data={"category": "<script>alert(1)</script>", "description": "x"})),
        ("POST", "/api/complaints", dict(data={"category": "pothole", "description": "A" * 1_000_000})),
        ("POST", "/api/complaints", dict(data={"category": "pothole", "description": "ok", "lat": "abc", "lon": "999"})),
        ("POST", "/api/complaints", dict(data={"category": "pothole", "description": "'; DROP TABLE defects;--"})),
        ("POST", "/api/complaints", dict(files={"files": ("a.jpg", b"not an image", "image/jpeg")}, data={"category": "pothole"})),
        ("POST", "/api/inspections", dict(files={"file": ("a.jpg", b"", "image/jpeg")})),
        ("POST", "/api/inspections", dict(files={"file": ("a.jpg", b"garbage" * 100, "image/jpeg")})),
        ("POST", "/api/inspections", dict(files={"file": ("a.exe", b"MZ" * 100, "application/octet-stream")})),
        ("POST", "/api/screening/check", dict(files={"file": ("a.jpg", b"garbage", "image/jpeg")})),
        ("GET", "/api/routeplan?origin=;;;&dest=%00", {}),
        ("GET", "/api/routeplan?origin=0,0&dest=0,0.0001", {}),
        ("GET", "/api/defects/99999999", {}),
        ("GET", "/api/defects/abc", {}),
        ("GET", "/media/../../.env", {}),
        ("GET", "/media/uploads/..%2f..%2f.env", {}),
        ("GET", "/api/complaints", {}),
        ("GET", "/api/jobs/doesnotexist", {}),
        ("POST", "/api/drive/frame", dict(data={"session_id": "nope"})),
        ("POST", "/api/defects/bulk-status", dict(json={"ids": [1], "status": "repaired"})),
    ]
    for m, p, kw in cases:
        try:
            r = await c.request(m, BASE + p, timeout=60, **kw)
            if r.status_code >= 500:
                bad5xx.append((m, p[:50], r.status_code))
            if p.startswith("/media/") and r.status_code == 200 and b"SUPABASE" in r.content:
                bad5xx.append(("LEAK", p, 200))
        except Exception as e:
            bad5xx.append((m, p[:50], str(e)[:40]))
    report("fuzz: malformed and hostile input never crashes or leaks", not bad5xx, str(bad5xx))
    alive = (await c.get(BASE + "/api/health")).status_code == 200
    report("server still healthy after fuzz", alive)


async def main():
    async with httpx.AsyncClient(limits=httpx.Limits(max_connections=200)) as c:
        h = await c.get(BASE + "/api/health")
        print("health:", h.status_code, h.text[:100])
        for fn in (read_load, ws_fanout, complaint_flood, screening, fuzz, route_burst, image_load, video_load, fall_alarm):
            try:
                await fn(c)
            except Exception as e:
                report(fn.__name__, False, f"exception {e!r}"[:200])
    fails = [r for r in results if not r[1]]
    print(f"\nSUMMARY: {len(results) - len(fails)} passed, {len(fails)} failed")
    for f in fails:
        print("  FAILED:", f[0], f[2])


asyncio.run(main())

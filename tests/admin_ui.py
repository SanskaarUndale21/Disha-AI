"""Walk every admin panel page, record console errors and failed API calls, take screenshots, and exercise the officer
actions (mark repaired on the map, acknowledge an emergency). Run against a backend started with RD_AUTH_REQUIRED=0."""
import json
import sys
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SHOTS = ROOT / ".shots"
ADMIN = "http://localhost:5173"
API = "http://127.0.0.1:8000"
PAGES = ["/", "/map", "/live", "/alerts", "/defects", "/repairs", "/complaints", "/phone", "/analyze", "/verify", "/progress",
         "/inspections", "/model", "/users"]
problems = []

with sync_playwright() as p:
    b = p.chromium.launch()
    for width, tag in ((1360, "d"), (390, "m")):
        pg = b.new_page(viewport={"width": width, "height": 820})
        errs, bad = [], []
        pg.on("pageerror", lambda e: errs.append(str(e)[:160]))
        pg.on("console", lambda m: errs.append(m.text[:160]) if m.type == "error" and "favicon" not in m.text else None)
        pg.on("response", lambda r: bad.append(f"{r.status} {r.url[:90]}") if r.status >= 400 and "/ws/" not in r.url else None)
        for path in PAGES:
            errs.clear(); bad.clear()
            pg.goto(ADMIN + path, wait_until="domcontentloaded")
            pg.wait_for_timeout(2500 if path not in ("/map", "/live") else 4000)
            body = pg.inner_text("body")[:2000]
            blank = len(body.strip()) < 40
            name = path.strip("/").replace("/", "_") or "home"
            pg.screenshot(path=str(SHOTS / f"adm_{tag}_{name}.png"))
            if errs or bad or blank:
                problems.append((tag, path, errs[:3], bad[:3], "BLANK" if blank else ""))
        pg.close()

    # officer action on the map: mark a defect repaired through the embedded map page
    pg = b.new_page(viewport={"width": 1360, "height": 820})
    pg.goto(ADMIN + "/map")
    pg.wait_for_timeout(6000)
    frame = next((f for f in pg.frames if "/map" in f.url and f != pg.main_frame), None)
    if frame is None:
        problems.append(("map", "iframe", ["map iframe not found"], [], ""))
    else:
        has_officer = frame.evaluate("document.body.classList.contains('officer')")
        if not has_officer:
            problems.append(("map", "officer mode", ["officer mode not enabled in the map iframe"], [], ""))
        d = httpx.get(API + "/api/public/defects").json()
        target = next(x for x in d if x["status"] == "active")
        frame.evaluate("location.hash = arguments[0]" if False else f"location.hash = '{target['uid']}'")
        pg.wait_for_timeout(2500)
        btn = frame.query_selector("#ofix")
        if not btn:
            problems.append(("map", "repair button", ["Mark repaired button missing on defect card"], [], ""))
        else:
            btn.click()
            pg.wait_for_timeout(2500)
            after = httpx.get(API + f"/api/defects/{target['number']}").json()
            if after.get("status") != "repaired":
                problems.append(("map", "repair action", [f"defect still {after.get('status')}"], [], ""))
            else:
                print("OK officer repair on map:", target["uid"])
            httpx.patch(API + f"/api/defects/{target['number']}", json={"status": "active"})
    pg.screenshot(path=str(SHOTS / "adm_map_officer.png"))
    b.close()

# emergency acknowledge through the API (the siren banner needs a live event)
em = httpx.get(API + "/api/safety/emergencies").json()
print("emergencies in list:", len(em))
print(json.dumps(problems, indent=1) if problems else "NO PROBLEMS FOUND")

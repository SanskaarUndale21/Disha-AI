"""Admin panel: a person-down event must show the flashing banner, start the siren, and be acknowledgeable.
Also checks the citizen portal and feed panel show the alarm. Backend must run with RD_AUTH_REQUIRED=0."""
import threading
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
API = "http://127.0.0.1:8000"
res = {}

def upload():
    httpx.post(API + "/api/inspections", files={"file": ("fall.mp4", (ROOT / "samples/fall_test.mp4").read_bytes(), "video/mp4")}, timeout=300)

with sync_playwright() as p:
    b = p.chromium.launch(args=["--autoplay-policy=no-user-gesture-required"])
    pages = {}
    for name, url in (("admin", "http://localhost:5173/defects"), ("citizen", "http://localhost:5174/"), ("feed", "http://localhost:5175/")):
        pg = b.new_page(viewport={"width": 1300, "height": 800})
        pg.add_init_script("""window.__audio = 0; const AC = window.AudioContext; if (AC) { window.AudioContext = function () { window.__audio++; return new AC(); }; }""")
        pg.goto(url); pg.wait_for_timeout(2500)
        for sel in ("text=Enable alarm sound", "button:has-text('Enable alarm sound')"):
            try:
                pg.click(sel, timeout=1500); break
            except Exception:
                pass
        pages[name] = pg
    n0 = len(httpx.get(API + "/api/safety/emergencies").json())
    t = threading.Thread(target=upload); t.start()
    import time
    t0 = time.time()
    while time.time() - t0 < 240 and len(httpx.get(API + "/api/safety/emergencies").json()) <= n0:
        time.sleep(2)
    res["emergency_recorded_after_s"] = round(time.time() - t0)
    for name, pg in pages.items():
        try:
            pg.wait_for_selector("[role=alertdialog], .fall-alarm, text=PERSON DOWN, text=Person down, text=EMERGENCY, text=Emergency", timeout=15000)
            res[name] = "banner shown"
        except Exception:
            res[name] = "NO BANNER"
        res[name] += f", audio contexts={pg.evaluate('window.__audio')}"
        pg.screenshot(path=str(ROOT / f".shots/alarm_{name}.png"))
    t.join()
    adm = pages["admin"]
    try:
        adm.click("button:has-text('Acknowledge')", timeout=5000); adm.wait_for_timeout(1500)
        em = httpx.get(API + "/api/safety/emergencies").json()
        res["ack"] = "acknowledged" if em and em[0]["status"] != "open" else f"still {em[0]['status'] if em else 'none'}"
    except Exception as e:
        res["ack"] = f"ack failed: {str(e)[:80]}"
    b.close()
print(res)

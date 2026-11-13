"""Real-time detection over WebSocket.

The browser streams JPEG frames (camera or a local video) and gets back tracked detections per frame:
stable IDs (ByteTrack, per connection), class, severity, risk, and the damage outline polygon from the OpenCV
analysis. Flow control is stop-and-wait, so latency never builds up.

Client -> server: binary JPEG frame | {"type":"config","cracks":bool} | {"type":"reset"} | {"type":"finish",...}
                  | {"type":"gps","lat","lon"}
Server -> client: {"type":"frame",...} | {"type":"saved",...} | {"type":"error",...}

Each frame also carries the safety layer (safety.py): "lane" (lane marking condition, computed every 3rd frame and
smoothed over ~15 results), "people" (pose model every 2nd frame) and, once per fall, "emergency".
"""
import asyncio
import json
import threading
import time
import uuid
from pathlib import Path

import cv2
import numpy as np

from . import config, detector, pipeline, safety, scoring


class LiveSession:
    def __init__(self, cracks=True):
        self.tk = detector.Tracker()
        self.cracks = cracks
        self.last_frame = None
        self.last_rows = []
        self.started = time.time()
        self.lane = safety.LaneSmoother(15)
        self.fall = safety.FallMonitor()
        self.people = []
        self.hazards = []
        self.want_people = True
        self.want_hazards = True
        self.gps = None  # (lat, lon) from the client

    def _safety(self, frame, out):
        """Lane markings every 3rd frame, people / falls every 2nd frame. Never breaks the detection stream."""
        n = self.tk.frame_idx
        res = {}
        try:
            if n % 3 == 1 or self.lane.last is None:
                self.lane.push(safety.lane_status(frame))
            res["lane"] = self.lane.value()
        except Exception as e:
            print(f"[live] lane check failed: {e!r}")
        try:
            if n % 2 == 1 and self.want_people:
                pots = [(t["id"], t["box"]) for t in out if t["cls"] == "pothole" and t["confirmed"] and t["id"] is not None]
                self.people, evs = self.fall.update(frame, pots)
                for ev in evs[:1]:
                    url = safety.snapshot(frame, ev)
                    lat, lon = self.gps if self.gps else (None, None)
                    em = safety.record_emergency(ev, url, lat, lon)
                    res["emergency"] = {"id": em["id"], "type": "fall_near_pothole" if ev["pothole_id"] is not None else "fall", "pothole_id": ev["pothole_id"],
                                        "message": em["message"], "snapshot_url": url}
            res["people"] = [{"box": p["box"], "fallen": p["fallen"]} for p in self.people]
        except Exception as e:
            print(f"[live] fall check failed: {e!r}")
        try:
            if n % 4 == 2 and self.want_hazards:
                self.hazards = safety.detect_hazards(frame)
            res["hazards"] = [{"box": [round(v, 1) for v in h["box"]], "kind": h["kind"], "label": h["label"], "conf": h["conf"]} for h in self.hazards]
        except Exception as e:
            print(f"[live] hazard check failed: {e!r}")
        return res

    def process(self, frame):
        t0 = time.time()
        rows = self.tk.step(frame, cracks=self.cracks)
        ms = (time.time() - t0) * 1000
        self.last_frame, self.last_rows = frame, rows
        out = []
        for r in rows:
            score, level, parts = scoring.risk(r["class_name"], r["severity_score"], lane=r["lane"], breakdown=True)
            out.append({"id": r["display_id"], "tid": r["track_id"], "cls": r["class_name"],
                        "conf": round(r["confidence"], 3), "tier": r.get("tier", "possible"),
                        "box": [round(r["x1"], 1), round(r["y1"], 1), round(r["x2"], 1), round(r["y2"], 1)],
                        "poly": r["polygon"], "severity": r["severity"], "sev": r["severity_score"],
                        "size": r["size_index"], "depth": r["depth_index"], "risk": level, "risk_score": score,
                        "risk_parts": parts, "hits": r["hits"], "confirmed": r["confirmed"]})
        res = {"type": "frame", "w": self.tk.w, "h": self.tk.h, "tracks": out, "unique": len(self.tk.unique()),
               "by_class": self.tk.by_class(), "infer_ms": round(ms, 1), "frame": self.tk.frame_idx,
               "cracks": self.cracks}
        res.update(self._safety(frame, out))
        res["safety_ms"] = round((time.time() - t0) * 1000 - ms, 1)
        return res


def save_session(sess: LiveSession, meta: dict):
    """Persist a live session as an inspection (media_type 'live') through the normal pipeline."""
    from .db import Inspection, SessionLocal, now
    rows = sess.tk.final_rows()
    s = SessionLocal()
    try:
        lat, lon = meta.get("lat"), meta.get("lon")
        insp = Inspection(media_type="live", original_name=f"live-session-{time.strftime('%Y%m%d-%H%M%S')}",
                          captured_at=now(), lat=lat, lon=lon,
                          location_source=(meta.get("location_source") or "manual") if lat is not None else "unknown",
                          road_name=meta.get("road_name"), road_type=meta.get("road_type") or "unknown",
                          traffic_level=meta.get("traffic_level") or "unknown", inspector=meta.get("inspector"),
                          frames_processed=sess.tk.frame_idx, width=sess.tk.w, height=sess.tk.h,
                          model_name=detector.model_info()["weights"])
        s.add(insp)
        s.flush()
        if sess.last_frame is not None:
            name = f"live_{uuid.uuid4().hex}.jpg"
            snap = detector.draw(sess.last_frame, [r for r in sess.last_rows if r["confirmed"]], detector.label_track)
            cv2.imwrite(str(config.ANNOTATED / name), snap, [cv2.IMWRITE_JPEG_QUALITY, 88])
            insp.annotated_path = str(config.ANNOTATED / name)
        dets = pipeline.register(s, insp, rows)
        insp.processing_ms = int((time.time() - sess.started) * 1000)
        insp.summary = dict(pipeline.summarize(dets), unique_tracks=len(rows), frames_processed=sess.tk.frame_idx)
        s.commit()
        return insp.id, [{"id": r["track_id"], "uid": d.defect.uid if d.defect else None, "duplicate": d.is_duplicate,
                          "risk": d.risk_score} for r, d in zip(rows, dets)]
    finally:
        s.close()


def register_ws(app):
    from fastapi import File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect

    safety.register(app)

    @app.post("/api/live/transcode")
    async def live_transcode(file: UploadFile = File(...)):
        """Convert a clip the browser cannot play (MPEG-4 Part 2, HEVC, AVI...) to H.264 MP4 for Live patrol."""
        import subprocess
        import imageio_ffmpeg
        src = config.UPLOADS / f"live_src_{uuid.uuid4().hex}{Path(file.filename or 'v.mp4').suffix or '.mp4'}"
        src.write_bytes(await file.read())
        dst = config.UPLOADS / f"live_{uuid.uuid4().hex}.mp4"
        cmd = [imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", "-i", str(src),
               "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-vf", "scale='min(1280,iw)':-2",
               "-an", "-movflags", "+faststart", str(dst)]
        r = await asyncio.to_thread(subprocess.run, cmd, capture_output=True, text=True, timeout=600)
        src.unlink(missing_ok=True)
        if r.returncode != 0 or not dst.exists():
            raise HTTPException(400, "This video could not be converted. Try an MP4 or MOV file.")
        return {"url": f"/media/uploads/{dst.name}"}

    @app.websocket("/ws/livestream")
    async def live_stream_ws(ws: WebSocket):
        """Server-side stream source: the server opens an IP camera / RTSP / HTTP (MJPEG, HLS) URL itself and sends back
        each analysed frame as {"image": <base64 jpeg>, ...same fields as /ws/live}. Client sends
        {"type":"start","url":"rtsp://...","classes":[...],"people":true,"hazards":true,"cracks":true} then {"type":"stop"}."""
        import base64
        await ws.accept()
        stop = threading.Event()
        q: asyncio.Queue = asyncio.Queue(maxsize=2)
        loop = asyncio.get_running_loop()

        def reader(url, cfg):
            cap = cv2.VideoCapture(url)
            if not cap.isOpened():
                loop.call_soon_threadsafe(q.put_nowait, {"type": "error", "error": "Could not open the stream. Check the address and that this computer can reach the camera."})
                return
            sess = LiveSession(bool(cfg.get("cracks", True)))
            if cfg.get("classes"):
                sess.tk.allow = set(cfg["classes"])
            sess.want_people = bool(cfg.get("people", True))
            sess.want_hazards = bool(cfg.get("hazards", True))
            if cfg.get("lat") is not None and cfg.get("lon") is not None:
                sess.gps = (float(cfg["lat"]), float(cfg["lon"]))
            last = 0.0
            try:
                while not stop.is_set():
                    ok, frame = cap.read()
                    if not ok:
                        loop.call_soon_threadsafe(q.put_nowait, {"type": "error", "error": "The stream ended or was interrupted."})
                        break
                    if time.time() - last < 0.12:  # about 8 analysed frames per second keeps the laptop cool
                        continue
                    last = time.time()
                    h, w = frame.shape[:2]
                    if max(h, w) > 960:
                        sc = 960 / max(h, w)
                        frame = cv2.resize(frame, (int(w * sc), int(h * sc)), interpolation=cv2.INTER_AREA)
                    res = sess.process(frame)
                    ok2, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                    if ok2:
                        res["image"] = base64.b64encode(buf.tobytes()).decode()
                        res["w"], res["h"] = frame.shape[1], frame.shape[0]
                    loop.call_soon_threadsafe(lambda r=res: q.full() or q.put_nowait(r))
            finally:
                cap.release()

        async def pump():
            while True:
                await ws.send_json(await q.get())

        pump_task = None
        thread = None
        try:
            pump_task = asyncio.create_task(pump())
            while True:
                msg = await ws.receive()
                if msg.get("type") == "websocket.disconnect":
                    break
                if not msg.get("text"):
                    continue
                m = json.loads(msg["text"])
                if m.get("type") == "start":
                    url = str(m.get("url", "")).strip()
                    if not url.lower().startswith(("rtsp://", "rtsps://", "http://", "https://")):
                        await ws.send_json({"type": "error", "error": "Use an rtsp://, http:// or https:// stream address."})
                        continue
                    stop.set()
                    if thread:
                        await asyncio.to_thread(thread.join, 3)
                    stop.clear()
                    thread = threading.Thread(target=reader, args=(url, m), daemon=True)
                    thread.start()
                    await ws.send_json({"type": "started"})
                elif m.get("type") == "stop":
                    stop.set()
        except Exception:
            pass
        finally:
            stop.set()
            if pump_task:
                pump_task.cancel()

    @app.websocket("/ws/live")
    async def live_ws(ws: WebSocket):
        await ws.accept()
        sess = await asyncio.to_thread(LiveSession)
        try:
            while True:
                msg = await ws.receive()
                if msg.get("type") == "websocket.disconnect":
                    break
                if msg.get("bytes") is not None:
                    frame = cv2.imdecode(np.frombuffer(msg["bytes"], np.uint8), cv2.IMREAD_COLOR)
                    if frame is None:
                        await ws.send_json({"type": "error", "error": "bad frame"})
                        continue
                    try:
                        await ws.send_json(await asyncio.to_thread(sess.process, frame))
                    except Exception as e:  # keep the stream alive, report the error
                        import traceback
                        traceback.print_exc()
                        await ws.send_json({"type": "error", "error": str(e)})
                elif msg.get("text"):
                    m = json.loads(msg["text"])
                    t = m.get("type")
                    if t == "config":
                        sess.cracks = bool(m.get("cracks", True))
                        if "classes" in m:
                            sess.tk.allow = set(m["classes"]) or None
                        if "people" in m:
                            sess.want_people = bool(m["people"])
                        if "hazards" in m:
                            sess.want_hazards = bool(m["hazards"])
                        await ws.send_json({"type": "config", "cracks": sess.cracks})
                    elif t == "gps":
                        try:
                            sess.gps = (float(m["lat"]), float(m["lon"]))
                        except (KeyError, TypeError, ValueError):
                            pass
                    elif t == "reset":
                        gps = sess.gps
                        sess = await asyncio.to_thread(LiveSession, sess.cracks)
                        sess.gps = gps
                        await ws.send_json({"type": "reset"})
                    elif t == "finish":
                        if not sess.tk.final_rows():
                            await ws.send_json({"type": "saved", "inspection_id": None, "defects": []})
                            continue
                        iid, mapping = await asyncio.to_thread(save_session, sess, m)
                        from . import events
                        events.publish("live.saved", {"inspection_id": iid, "defects": len(mapping),
                                                      "new": sum(1 for x in mapping if not x["duplicate"])})
                        await ws.send_json({"type": "saved", "inspection_id": iid, "defects": mapping})
                        gps = sess.gps
                        sess = await asyncio.to_thread(LiveSession, sess.cracks)
                        sess.gps = gps
        except WebSocketDisconnect:
            pass

"""Real-time detection over WebSocket.

The browser streams JPEG frames (camera or a local video) and gets back tracked detections per frame:
stable IDs (ByteTrack, per connection), class, severity, risk, and the damage outline polygon from the OpenCV
analysis. Flow control is stop-and-wait, so latency never builds up.

Client -> server: binary JPEG frame | {"type":"config","cracks":bool} | {"type":"reset"} | {"type":"finish",...}
Server -> client: {"type":"frame",...} | {"type":"saved",...} | {"type":"error",...}
"""
import asyncio
import json
import time
import uuid
from pathlib import Path

import cv2
import numpy as np

from . import config, detector, pipeline, scoring


class LiveSession:
    def __init__(self, cracks=True):
        self.tk = detector.Tracker()
        self.cracks = cracks
        self.last_frame = None
        self.last_rows = []
        self.started = time.time()

    def process(self, frame):
        t0 = time.time()
        rows = self.tk.step(frame, cracks=self.cracks)
        ms = (time.time() - t0) * 1000
        self.last_frame, self.last_rows = frame, rows
        out = []
        for r in rows:
            score, level, parts = scoring.risk(r["class_name"], r["severity_score"], lane=r["lane"], breakdown=True)
            out.append({"id": r["display_id"], "tid": r["track_id"], "cls": r["class_name"],
                        "conf": round(r["confidence"], 3),
                        "box": [round(r["x1"], 1), round(r["y1"], 1), round(r["x2"], 1), round(r["y2"], 1)],
                        "poly": r["polygon"], "severity": r["severity"], "sev": r["severity_score"],
                        "size": r["size_index"], "depth": r["depth_index"], "risk": level, "risk_score": score,
                        "risk_parts": parts, "hits": r["hits"], "confirmed": r["confirmed"]})
        return {"type": "frame", "w": self.tk.w, "h": self.tk.h, "tracks": out, "unique": len(self.tk.unique()),
                "by_class": self.tk.by_class(), "infer_ms": round(ms, 1), "frame": self.tk.frame_idx,
                "cracks": self.cracks}


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
                        await ws.send_json({"type": "config", "cracks": sess.cracks})
                    elif t == "reset":
                        sess = await asyncio.to_thread(LiveSession, sess.cracks)
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
                        sess = await asyncio.to_thread(LiveSession, sess.cracks)
        except WebSocketDisconnect:
            pass

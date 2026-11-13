"""Realtime event bus: every state change is pushed to connected clients over WebSocket (/ws/events).

publish() is safe to call from sync request handlers and worker threads. Each event:
  {"type": "complaint.created", "data": {...}, "ts": "...", "audience": "officer"|"all"|"user:<id>"}
Officer consoles receive everything; citizen clients receive "all" events and those addressed to them
(e.g. "complaint.updated" for their own complaint), so a citizen sees their status change the moment an
officer acts.

Event types: inspection.created, inspection.processed, defect.created, defect.updated, detection.verified,
complaint.created, complaint.updated, live.saved
"""
import asyncio
import json
import threading
from datetime import datetime, timezone

_loop: asyncio.AbstractEventLoop | None = None
_clients: dict = {}  # websocket -> {"role": str, "user_id": str | None}
_lock = threading.Lock()
_recent: list = []


def _default(o):
    if isinstance(o, datetime):
        return o.isoformat()
    return str(o)


def publish(type_: str, data: dict | None = None, audience: str = "officer"):
    ev = {"type": type_, "data": data or {}, "audience": audience,
          "ts": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    with _lock:
        _recent.append(ev)
        del _recent[:-50]
    if _loop is None:
        return
    msg = json.dumps(ev, default=_default)
    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        running = None
    try:
        if running is _loop:
            _loop.create_task(_fanout(msg, audience))
        else:
            asyncio.run_coroutine_threadsafe(_fanout(msg, audience), _loop)
    except RuntimeError:
        pass


def _wants(info, audience):
    if info["role"] in ("officer", "admin"):
        return True
    if audience == "all":
        return True
    return audience.startswith("user:") and info.get("user_id") == audience[5:]


async def _fanout(msg, audience):
    dead = []
    for ws, info in list(_clients.items()):
        if not _wants(info, audience):
            continue
        try:
            await ws.send_text(msg)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _clients.pop(ws, None)


def register(app):
    from fastapi import WebSocket, WebSocketDisconnect

    from . import auth, config

    @app.on_event("startup")
    async def _bind_loop():
        global _loop
        _loop = asyncio.get_running_loop()

    @app.websocket("/ws/events")
    async def events_ws(ws: WebSocket):
        await ws.accept()
        role, uid = "public", None
        token = ws.query_params.get("token")
        if token:
            try:
                prof = await asyncio.to_thread(auth.optional_user, f"Bearer {token}")
                if prof:
                    role, uid = prof["role"], prof["id"]
            except Exception:
                await ws.send_json({"type": "auth.error"})
        if not config.AUTH_REQUIRED and role == "public":
            role = "officer"  # open demo mode
        _clients[ws] = {"role": role, "user_id": uid}
        await ws.send_json({"type": "hello", "data": {"role": role, "clients": len(_clients)},
                            "recent": [e for e in _recent[-20:] if _wants(_clients[ws], e["audience"])]})
        try:
            while True:
                await ws.receive_text()  # keepalive pings from client
        except WebSocketDisconnect:
            pass
        finally:
            _clients.pop(ws, None)

    from fastapi import Depends

    @app.get("/api/events/recent")
    def recent(_u=Depends(auth.require_officer)):
        return _recent[-50:]

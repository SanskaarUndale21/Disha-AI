"""Pre-submission screening of citizen media: no visible road damage, no complaint.

Flow
  1. The app sends each photo/video to POST /api/screening/check before the citizen can submit.
     Images run through the detection ensemble; videos are sampled at 8 frames across the clip.
     The check passes when road damage is found with enough confidence; the response carries an
     annotated preview so the citizen sees what was detected, plus a one-time `token`.
  2. POST /api/complaints re-validates on the server: every uploaded file must match a recent passing
     check (by token and content hash) or it is screened inline. Media that shows no damage is refused,
     so a modified app cannot bypass the check.
  3. Abuse control: 5 failed checks from one device or phone number within 60 minutes blocks further
     checks from it for an hour (verdict "rate_limited").
Every check is stored (screening_checks) and pushed live to the officer dashboard.
"""
import hashlib
import json
import tempfile
import time
import uuid
from datetime import timedelta
from typing import Optional

import cv2
import numpy as np
from fastapi import Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import JSON, Boolean, Column, DateTime, Float, Integer, String, Text

from . import auth, config, detector, events
from .db import Base, SessionLocal, engine, now

# what counts as reportable road damage, and the confidence each needs
DAMAGE_MIN_CONF = {"pothole": 0.35, "alligator_crack": 0.35, "transverse_crack": 0.4, "longitudinal_crack": 0.4,
                   "debris": 0.5, "manhole": 0.55}
FAIL_LIMIT, FAIL_WINDOW_MIN, BLOCK_MIN = 5, 60, 60
TOKEN_TTL_MIN = 60
VIDEO_SAMPLES = 8


class ScreeningCheck(Base):
    __tablename__ = "screening_checks"
    id = Column(Integer, primary_key=True)
    token = Column(String(40), unique=True, index=True)
    created_at = Column(DateTime, default=now, index=True)
    device_id = Column(String(64), index=True)
    phone = Column(String(20), index=True)
    user_id = Column(String(64), index=True)
    media_type = Column(String(10))
    filename = Column(String(255))
    sha256 = Column(String(64), index=True)
    verdict = Column(String(16), index=True)  # pass | fail | rate_limited
    reason = Column(Text)
    max_conf = Column(Float)
    detections = Column(JSON)
    preview_path = Column(String(512))
    complaint_id = Column(Integer, nullable=True, index=True)
    used = Column(Boolean, default=False)
    source = Column(String(16), default="app")  # app | server (inline check at submit)


def _local(dt):
    """Stored times are UTC; show the citizen their local clock time."""
    from datetime import datetime
    return dt + (datetime.now() - datetime.utcnow())


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _damage(rows):
    found = []
    for r in rows:
        need = DAMAGE_MIN_CONF.get(r["class_name"])
        if need is not None and r["confidence"] >= need:
            found.append(r)
    return found


def _analyse_frame(img):
    proc, _ = detector.preprocess(img)
    d = detector.infer(proc)
    return detector.rows_from(img, d)


def _analyse(data: bytes, filename: str):
    """Returns (media_type, damage_rows, all_rows, preview_bgr)."""
    ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if img is not None:
        rows = _analyse_frame(img)
        dmg = _damage(rows)
        return "image", dmg, rows, detector.draw(img, dmg or rows)
    # video: sample frames evenly
    with tempfile.NamedTemporaryFile(suffix=ext or ".mp4", delete=False) as tf:
        tf.write(data)
        path = tf.name
    cap = cv2.VideoCapture(path)
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if n <= 0:
        cap.release()
        raise HTTPException(400, "This file can't be read. Use a JPG or PNG photo, or an MP4 or MOV video.")
    best, best_rows, best_dmg, all_dmg = None, [], [], []
    for i in np.linspace(0, max(0, n - 1), VIDEO_SAMPLES).astype(int):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(i))
        ok, fr = cap.read()
        if not ok:
            continue
        rows = _analyse_frame(fr)
        dmg = _damage(rows)
        all_dmg += dmg
        if best is None or len(dmg) > len(best_dmg):
            best, best_rows, best_dmg = fr, rows, dmg
    cap.release()
    if best is None:
        raise HTTPException(400, "This video can't be read. Try recording it again.")
    return "video", all_dmg, best_rows, detector.draw(best, best_dmg or best_rows)


def _recent_fails(s, device_id, phone):
    since = now() - timedelta(minutes=FAIL_WINDOW_MIN)
    q = s.query(ScreeningCheck).filter(ScreeningCheck.created_at >= since, ScreeningCheck.verdict == "fail")
    keys = []
    if device_id:
        keys.append(ScreeningCheck.device_id == device_id)
    if phone:
        keys.append(ScreeningCheck.phone == phone)
    if not keys:
        return []
    from sqlalchemy import or_
    return q.filter(or_(*keys)).order_by(ScreeningCheck.created_at.desc()).all()


def blocked_until(s, device_id, phone):
    fails = _recent_fails(s, device_id, phone)
    if len(fails) >= FAIL_LIMIT:
        return fails[FAIL_LIMIT - 1].created_at + timedelta(minutes=BLOCK_MIN)
    return None


def ser(c: ScreeningCheck, base=""):
    return {
        "id": c.id, "token": c.token, "created_at": c.created_at, "verdict": c.verdict, "reason": c.reason,
        "media_type": c.media_type, "filename": c.filename, "max_confidence": c.max_conf,
        "damage": c.detections or [], "complaint_id": c.complaint_id, "source": c.source,
        "device": (c.device_id[:6] + "...") if c.device_id else None,
        "phone": (c.phone[:2] + "x" * max(0, len(c.phone) - 4) + c.phone[-2:]) if c.phone and len(c.phone) > 4 else None,
        "preview_url": f"/media/annotated/{c.preview_path}" if c.preview_path else None,
    }


def run_check(data: bytes, filename: str, device_id=None, phone=None, user_id=None, source="app"):
    s = SessionLocal()
    try:
        until = blocked_until(s, device_id, phone)
        if until and until > now():
            c = ScreeningCheck(token=uuid.uuid4().hex, device_id=device_id, phone=phone, user_id=user_id,
                               filename=filename, sha256=_sha(data), verdict="rate_limited", source=source,
                               reason=f"Too many photos without road damage. Try again after {_local(until):%H:%M}.")
            s.add(c)
            s.commit()
            out = ser(c)
            out["blocked_until"] = until
            events.publish("screening.checked", out)
            return out
        mtype, dmg, rows, preview = _analyse(data, filename)
        ai = {"ai": False, "score": None}
        if mtype == "image":
            from . import aigen
            ai = aigen.check(data)
        name = f"scr_{uuid.uuid4().hex}.jpg"
        cv2.imwrite(str(config.ANNOTATED / name), preview, [cv2.IMWRITE_JPEG_QUALITY, 85])
        summary = {}
        for r in dmg:
            summary[r["class_name"]] = summary.get(r["class_name"], 0) + 1
        ok = bool(dmg) and not ai["ai"]
        if ai["ai"]:
            reason = ai["reason"] + " Reports must use real photos taken at the road. AI generated images are not accepted."
        elif ok:
            parts = [f"{v} {k.replace('_', ' ')}{'s' if v > 1 else ''}" for k, v in summary.items()]
            reason = "Road damage found: " + ", ".join(parts)
        elif rows:
            reason = "Only weak signs of damage were found. Move closer and photograph the damaged area clearly."
        else:
            reason = "No road damage was found in this photo. Photograph the pothole or crack itself, in daylight if possible."
        c = ScreeningCheck(token=uuid.uuid4().hex, device_id=device_id, phone=phone, user_id=user_id, media_type=mtype,
                           filename=filename, sha256=_sha(data), verdict="pass" if ok else "fail", reason=reason,
                           max_conf=round(max([r["confidence"] for r in dmg], default=max([r["confidence"] for r in rows], default=0.0)), 3),
                           detections=[{"class": r["class_name"], "confidence": round(r["confidence"], 3),
                                        "severity": r.get("severity")} for r in (dmg or rows)][:20],
                           preview_path=name, source=source)
        s.add(c)
        s.commit()
        out = ser(c)
        if not ok:
            left = FAIL_LIMIT - len(_recent_fails(s, device_id, phone))
            if left <= 2 and (device_id or phone):
                out["warning"] = f"{max(0, left)} more photos without damage and reporting is paused for an hour."
        events.publish("screening.checked", out)
        return out
    finally:
        s.close()


def enforce(file_blobs, tokens, device_id=None, phone=None, user_id=None):
    """Called by POST /api/complaints before anything is stored. file_blobs: list of (filename, bytes).
    Each file needs a matching passing check (token + same content) or is screened inline now.
    Raises 422 when any file shows no road damage, 429 when the device is rate limited.
    Returns the list of check ids to link to the complaint."""
    s = SessionLocal()
    try:
        until = blocked_until(s, device_id, phone)
        if until and until > now():
            raise HTTPException(429, f"Too many photos without road damage. Reporting resumes after {_local(until):%H:%M}.")
        valid = {}
        cutoff = now() - timedelta(minutes=TOKEN_TTL_MIN)
        for t in tokens or []:
            c = s.query(ScreeningCheck).filter(ScreeningCheck.token == t).first()
            if c and c.verdict == "pass" and not c.used and c.created_at >= cutoff:
                valid[c.sha256] = c.id
    finally:
        s.close()
    ids = []
    for name, data in file_blobs:
        h = _sha(data)
        if h in valid:
            ids.append(valid[h])
            continue
        out = run_check(data, name, device_id, phone, user_id, source="server")
        if out["verdict"] == "rate_limited":
            raise HTTPException(429, out["reason"])
        if out["verdict"] != "pass":
            raise HTTPException(422, f"{name}: {out['reason']}")
        ids.append(out["id"])
    return ids


def link(check_ids, complaint_id):
    if not check_ids:
        return
    s = SessionLocal()
    try:
        for c in s.query(ScreeningCheck).filter(ScreeningCheck.id.in_(check_ids)).all():
            c.complaint_id, c.used = complaint_id, True
        s.commit()
    finally:
        s.close()


def register(app):
    Base.metadata.create_all(engine, tables=[ScreeningCheck.__table__])

    @app.post("/api/screening/check")
    async def screening_check(file: UploadFile = File(...), device_id: Optional[str] = Form(None),
                              phone: Optional[str] = Form(None), user: Optional[dict] = Depends(auth.optional_user)):
        """Run before submitting a complaint. Returns verdict pass | fail | rate_limited, what was found,
        an annotated preview and a one-time token to send with the complaint."""
        import asyncio
        data = await file.read()
        if not data:
            raise HTTPException(400, "Empty file")
        name = file.filename or "upload.jpg"
        if "." not in name:
            name += ".mp4" if (file.content_type or "").startswith("video/") else ".jpg"
        phone = phone or (user or {}).get("phone")
        return await asyncio.to_thread(run_check, data, name, device_id, phone, (user or {}).get("id"))

    @app.get("/api/screening/checks", dependencies=[Depends(auth.require_officer)])
    def screening_list(verdict: Optional[str] = None, limit: int = 60):
        s = SessionLocal()
        try:
            q = s.query(ScreeningCheck)
            if verdict:
                q = q.filter(ScreeningCheck.verdict == verdict)
            return [ser(c) for c in q.order_by(ScreeningCheck.created_at.desc()).limit(min(limit, 300)).all()]
        finally:
            s.close()

    @app.get("/api/screening/stats")
    def screening_stats():
        s = SessionLocal()
        try:
            day = now() - timedelta(hours=24)
            rows = s.query(ScreeningCheck).filter(ScreeningCheck.created_at >= day).all()
            tot = len(rows)
            by = {v: sum(1 for r in rows if r.verdict == v) for v in ("pass", "fail", "rate_limited")}
            dev = {}
            for r in rows:
                key = r.device_id or r.phone
                if not key or r.verdict == "pass":
                    continue
                d = dev.setdefault(key, {"device": (key[:6] + "...") if r.device_id else ser(r)["phone"],
                                         "blocked_attempts": 0, "fails": 0, "last": r.created_at})
                d["fails"] += r.verdict == "fail"
                d["blocked_attempts"] += r.verdict == "rate_limited"
                d["last"] = max(d["last"], r.created_at)
            flagged = sorted([d for d in dev.values() if d["fails"] >= 3 or d["blocked_attempts"]],
                             key=lambda d: -(d["fails"] + d["blocked_attempts"]))[:10]
            return {"last_24h": tot, "passed": by["pass"], "failed": by["fail"], "rate_limited": by["rate_limited"],
                    "pass_rate": round(by["pass"] / tot, 3) if tot else None, "flagged_devices": flagged,
                    "rules": {"fail_limit": FAIL_LIMIT, "window_min": FAIL_WINDOW_MIN, "block_min": BLOCK_MIN,
                              "min_confidence": DAMAGE_MIN_CONF}}
        finally:
            s.close()

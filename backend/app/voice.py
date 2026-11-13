"""Phone complaint intake (voice agent call-end webhook) and evidence-based verification.

Verification ladder (never downgraded):
  unverified      a call was received, nothing else known
  corroborated    an AI-detected defect or another independent caller lies within 150 m
  photo_verified  the citizen uploaded a photo/video through the SMS upload link and the AI found damage
  field_verified  an officer checked the spot

Extra fields live in our own table `complaint_meta` (one row per complaint) so db.py stays untouched.
Geocoding uses OpenStreetMap Nominatim (free, max 1 request per second) with a local cache table.
"""
import html
import json
import os
import re
import threading
import time
import urllib.parse
import urllib.request
from datetime import timedelta
from math import cos, radians
from pathlib import Path
from typing import Any, Optional

from fastapi import Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import JSON, Column, DateTime, Float, ForeignKey, Integer, String, Text

from . import auth, events
from .db import Base, Complaint, ComplaintMedia, Defect, Detection, Inspection, SessionLocal, engine, now  # noqa: F401
from .geo import haversine_m

LEVELS = ("unverified", "corroborated", "photo_verified", "field_verified")
RANK = {k: i for i, k in enumerate(LEVELS)}
RADIUS_M = 150.0
NOMINATIM = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "Disha AI/1.0 (municipal road monitoring)"
STATIC = Path(__file__).parent / "static"


class ComplaintMeta(Base):
    __tablename__ = "complaint_meta"
    complaint_id = Column(Integer, ForeignKey("complaints.id"), primary_key=True)
    source = Column(String(10), default="phone")  # phone | app | web
    verification = Column(String(20), default="unverified")
    evidence = Column(JSON, default=list)
    call_id = Column(String(120), index=True, nullable=True)
    transcript_summary = Column(Text)
    location_text = Column(String(300))
    landmark = Column(String(200))
    geocode_source = Column(String(20), default="none")  # nominatim | gps | none
    issue_type = Column(String(80))
    urgency = Column(String(10), default="normal")  # high | normal
    updated_at = Column(DateTime, default=now)


class GeocodeCache(Base):
    __tablename__ = "geocode_cache"
    query = Column(String(400), primary_key=True)
    lat = Column(Float, nullable=True)
    lon = Column(Float, nullable=True)
    display_name = Column(String(500))
    created_at = Column(DateTime, default=now)


# ---------- payload parsing ----------
FIELDS = ("caller_name", "caller_phone", "location_text", "landmark", "area_city", "issue_type",
          "severity_description", "duration_text", "summary", "call_id")
ALIASES = {
    "caller_phone": ("caller_phone", "from", "from_number", "caller", "caller_number", "user_identifier",
                     "phone_number", "phone", "mobile"),
    "call_id": ("call_id", "callid", "call_sid", "conversation_id", "interaction_id", "session_id"),
    "summary": ("summary", "transcript_summary", "call_summary"),
    "area_city": ("area_city", "area", "city"),
}
CONTAINERS = ("agent_variables", "variables", "extracted_variables", "data")


def _norm(k: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(k).lower())


def _scalar(v):
    if v is None or isinstance(v, (dict, list)):
        return None
    v = str(v).strip()
    return v if v and v.lower() not in ("null", "none", "n/a", "na", "unknown") else None


def _pairs(obj):
    """Yield (key, value) at every depth, breadth first, so shallower values win.
    Also understands lists of {"name"/"key": k, "value": v} entries."""
    queue = [obj]
    while queue:
        cur = queue.pop(0)
        if isinstance(cur, dict):
            nk = cur.get("name") or cur.get("key") or cur.get("variable")
            if isinstance(nk, str) and "value" in cur:
                yield nk, cur["value"]
            # look inside the known containers first
            items = sorted(cur.items(), key=lambda kv: 0 if _norm(kv[0]) in {_norm(c) for c in CONTAINERS} else 1)
            for k, v in items:
                yield k, v
                if isinstance(v, (dict, list)):
                    queue.append(v)
                elif isinstance(v, str) and v.strip()[:1] in "{[":
                    try:
                        queue.append(json.loads(v))
                    except ValueError:
                        pass
        elif isinstance(cur, list):
            queue.extend(x for x in cur if isinstance(x, (dict, list)))


def _find(payload, names):
    wanted = [_norm(n) for n in names]
    found = {}
    for k, v in _pairs(payload):
        nk = _norm(k)
        if nk in wanted and nk not in found:
            sv = _scalar(v)
            if sv is not None:
                found[nk] = sv
    for w in wanted:  # alias order = priority
        if w in found:
            return found[w]
    return None


def extract_call(payload: Any) -> dict:
    return {f: _find(payload, ALIASES.get(f, (f,))) for f in FIELDS}


# ---------- helpers ----------
def _digits(p) -> str:
    return re.sub(r"\D", "", p or "")


def mask_phone(p) -> Optional[str]:
    d = _digits(p)
    if len(d) == 12 and d.startswith("91"):
        d = d[2:]
    if len(d) < 6:
        return "x" * len(d) if d else None
    return d[:2] + "x" * (len(d) - 4) + d[-2:]


def category_for(issue: Optional[str]) -> str:
    t = (issue or "").lower()
    if not t:
        return "pothole"
    if "manhole" in t or "sewer" in t or "drain cover" in t:
        return "manhole"
    if any(w in t for w in ("pothole", "pot hole", "gadda", "gaddha", "hole", "pit")):
        return "pothole"
    if "crack" in t:
        return "crack"
    if any(w in t for w in ("water", "flood", "logging", "drain", "puddle")):
        return "waterlogging"
    return "other"


HIGH_WORDS = ("big", "deep", "dangerous", "danger", "accident", "very", "huge", "large", "severe", "injur",
              "fell", "fall", "urgent", "bahut", "bada")


def urgency_for(*texts) -> str:
    t = " ".join(x for x in texts if x).lower()
    return "high" if any(re.search(rf"\b{w}", t) for w in HIGH_WORDS) else "normal"


def _clean_place(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    s = re.sub(r"^(near|opposite|opp\.?|behind|next to|beside|in front of|close to)\s+", "", s.strip(), flags=re.I)
    return s.strip(" ,.") or None


def _base(request: Request) -> str:
    return (os.getenv("RD_PUBLIC_URL") or str(request.base_url)).rstrip("/")


# ---------- geocoding (Nominatim, cached, 1 req/s) ----------
_geo_lock = threading.Lock()
_geo_last = [0.0]


def _nominatim(q: str):
    with _geo_lock:
        wait = 1.05 - (time.time() - _geo_last[0])
        if wait > 0:
            time.sleep(wait)
        url = NOMINATIM + "?" + urllib.parse.urlencode(
            {"format": "jsonv2", "limit": 1, "countrycodes": "in", "q": q})
        try:
            r = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": USER_AGENT}), timeout=8)
            rows = json.loads(r.read().decode("utf-8"))
        except Exception as e:  # noqa
            print(f"geocode failed for {q!r}: {e}")
            return None, False
        finally:
            _geo_last[0] = time.time()
    if rows:
        return (float(rows[0]["lat"]), float(rows[0]["lon"]), rows[0].get("display_name")), True
    return None, True


def geocode(s, q: str):
    """Returns (lat, lon, display_name) or None. Only location text ever goes to the geocoder."""
    q = re.sub(r"\s+", " ", (q or "").strip(" ,"))[:400]
    if not q:
        return None
    key = q.lower()
    hit = s.get(GeocodeCache, key)
    if hit is not None:
        return (hit.lat, hit.lon, hit.display_name) if hit.lat is not None else None
    res, ok = _nominatim(q)
    if ok:  # cache answers (also "no result"), not network errors
        s.merge(GeocodeCache(query=key, lat=res[0] if res else None, lon=res[1] if res else None,
                             display_name=res[2] if res else None, created_at=now()))
        s.commit()
    return res


def geocode_call(s, loc, landmark, city):
    loc_c, lm_c = _clean_place(loc), _clean_place(landmark)
    tries = []
    for parts in ((loc_c, lm_c, city), (lm_c, city), (loc_c, city)):
        q = ", ".join(p for p in parts if p)
        if q and q not in tries and any(parts[:-1]):
            tries.append(q)
    for q in tries:
        res = geocode(s, q)
        if res:
            return res
    return None


# ---------- verification ----------
def _raise(meta, level, evidence=None):
    if RANK.get(level, 0) > RANK.get(meta.verification or "unverified", 0):
        meta.verification = level
    if evidence:
        ev = [e for e in (meta.evidence or []) if e != evidence]
        meta.evidence = ev + [evidence]
    meta.updated_at = now()


def _near(lat, lon, rows, radius=RADIUS_M):
    out = []
    for r in rows:
        if r.lat is None or r.lon is None:
            continue
        d = haversine_m(lat, lon, r.lat, r.lon)
        if d <= radius:
            out.append((d, r))
    return sorted(out, key=lambda x: x[0])


def corroborate(s, c: Complaint, meta: ComplaintMeta) -> bool:
    """Look for independent evidence near the complaint. Returns True if meta changed."""
    if c.lat is None or c.lon is None:
        return False
    before = (meta.verification, list(meta.evidence or []))
    dlat = RADIUS_M / 111000.0 * 1.2
    dlon = dlat / max(cos(radians(c.lat)), 0.1)
    box = lambda M: (M.lat.between(c.lat - dlat, c.lat + dlat), M.lon.between(c.lon - dlon, c.lon + dlon))  # noqa
    new_ev = []
    own = {m.inspection_id for m in c.media if m.inspection_id}
    own_defects = {d.defect_id for d in s.query(Detection).filter(Detection.inspection_id.in_(own)).all()} if own else set()
    defects = _near(c.lat, c.lon, [d for d in s.query(Defect).filter(Defect.status == "active", *box(Defect)).all()
                                   if d.id not in own_defects])  # the citizen's own photo is not independent
    if defects:
        d, df = defects[0]
        more = f" (+{len(defects) - 1} more)" if len(defects) > 1 else ""
        new_ev.append(f"AI-detected defect {df.uid} within {int(round(d))} m{more}")
    others = s.query(Complaint).filter(Complaint.id != c.id, Complaint.status != "rejected", *box(Complaint)).all()
    mine = _digits(c.citizen_phone)[-10:]
    callers = set()
    for d, o in _near(c.lat, c.lon, others):
        theirs = _digits(o.citizen_phone)[-10:]
        if mine and theirs == mine:
            continue
        callers.add(theirs or f"anon-{o.id}")
    if callers:
        new_ev.append(f"{len(callers) + 1} independent reports within {int(RADIUS_M)} m")
    # refresh our own corroboration lines (counts and distances can change), keep everything else
    keep = [e for e in (meta.evidence or []) if not (e.startswith("AI-detected defect ")
                                                     or e.endswith(f"independent reports within {int(RADIUS_M)} m"))]
    meta.evidence = keep + new_ev
    if new_ev and RANK.get(meta.verification or "unverified", 0) < RANK["corroborated"]:
        meta.verification = "corroborated"
    changed = (meta.verification, list(meta.evidence)) != before
    if changed:
        meta.updated_at = now()
    return changed


def _meta_for(s, c: Complaint, source="web") -> ComplaintMeta:
    m = s.get(ComplaintMeta, c.id)
    if m is None:
        m = ComplaintMeta(complaint_id=c.id, source=source, verification="unverified", evidence=[],
                          geocode_source="gps" if c.lat is not None else "none", updated_at=now())
        s.add(m)
        s.flush()
    return m


# ---------- intake ----------
def create_from_call(s, call: dict, base: str) -> dict:
    call_id = call.get("call_id")
    if call_id:
        m = s.query(ComplaintMeta).filter(ComplaintMeta.call_id == call_id).first()
        if m is not None:
            c = s.get(Complaint, m.complaint_id)
            if c is not None:
                return dict(_result(c, m, base), duplicate=True)
    loc, lm, city = call.get("location_text"), call.get("landmark"), call.get("area_city")
    issue, sev = call.get("issue_type"), call.get("severity_description")
    if not any((loc, lm, issue, sev, call.get("summary"))):
        raise HTTPException(400, "call has no location or issue details")
    geo = geocode_call(s, loc, lm, city)
    raw_addr = ", ".join(p for p in (loc, f"near {_clean_place(lm)}" if lm else None, city) if p)
    desc_parts = [p for p in (issue, sev) if p]
    if call.get("duration_text"):
        desc_parts.append(f"present for {call['duration_text']}")
    desc = ". ".join(desc_parts) or (call.get("summary") or "")
    phone = (call.get("caller_phone") or "").strip()[:20] or None
    c = Complaint(category=category_for(issue), description=desc[:2000], citizen_name=(call.get("caller_name") or None),
                  citizen_phone=phone, lat=geo[0] if geo else None, lon=geo[1] if geo else None,
                  address=(((geo[2] if geo else None) or raw_addr or "")[:255]) or None)
    s.add(c)
    s.commit()
    c.ticket = f"RW-{c.id:06d}"
    m = ComplaintMeta(complaint_id=c.id, source="phone", verification="unverified", evidence=["voice call"],
                      call_id=call_id, transcript_summary=call.get("summary"),
                      location_text=", ".join(p for p in (loc, city) if p) or None, landmark=lm,
                      geocode_source="nominatim" if geo else "none", issue_type=issue,
                      urgency=urgency_for(issue, sev, call.get("summary")), updated_at=now())
    s.add(m)
    s.commit()
    corroborate(s, c, m)
    s.commit()
    events.publish("complaint.created", {
        "id": c.id, "ticket": c.ticket, "category": c.category, "description": c.description, "lat": c.lat,
        "lon": c.lon, "address": c.address, "status": c.status, "source": "phone",
        "verification": m.verification, "urgency": m.urgency})
    res = _result(c, m, base)
    res["sms"] = send_intake_sms(phone, c.ticket, res["upload_url"])
    res["evidence_deadline"] = deadline_for(c, m).isoformat() + "Z"
    m.evidence = list(m.evidence or []) + [f"intake SMS {'sent' if res['sms']['sent'] else 'not sent: ' + str(res['sms']['reason'])}"]
    s.commit()
    return res


def _result(c, m, base):
    return {"ticket": c.ticket, "complaint_id": c.id, "verification": m.verification, "lat": c.lat, "lon": c.lon,
            "address": c.address, "upload_url": f"{base}/upload/{c.ticket}"}


def ser_queue(c: Complaint, m: ComplaintMeta, base: str) -> dict:
    return {
        "complaint_id": c.id, "ticket": c.ticket, "created_at": c.created_at, "caller_name": c.citizen_name,
        "caller_phone": mask_phone(c.citizen_phone), "location_text": m.location_text, "landmark": m.landmark,
        "address": c.address, "lat": c.lat, "lon": c.lon, "issue_type": m.issue_type, "category": c.category,
        "description": c.description, "urgency": m.urgency, "verification": m.verification,
        "evidence": list(m.evidence or []), "status": c.status, "upload_url": f"{base}/upload/{c.ticket}",
        "media_count": len(c.media), "geocode_source": m.geocode_source, "summary": m.transcript_summary,
        "updated_at": m.updated_at,
    }


def _needs_check(c, m):
    return m.verification in ("unverified", "corroborated") and c.status not in ("resolved", "rejected")


# ---------- 6 hour evidence window ----------
EVIDENCE_WINDOW_H = 6
REMIND_AT_H = 5  # one reminder SMS an hour before the deadline


def deadline_for(c: Complaint, m: Optional[ComplaintMeta]):
    """Phone complaints must get a photo or video within 6 hours of the call, or they are cancelled."""
    if m is None or m.source != "phone" or c.created_at is None:
        return None
    return c.created_at + timedelta(hours=EVIDENCE_WINDOW_H)


def awaiting_evidence(c: Complaint, m: Optional[ComplaintMeta]) -> bool:
    return bool(m and m.source == "phone" and c.status == "submitted" and not c.media)


def sms_text_new(ticket: str, url: str) -> str:
    return (f"Disha AI: your complaint {ticket} is filed. To verify the road damage, open this link and add a photo or "
            f"video within {EVIDENCE_WINDOW_H} hours, otherwise the complaint is cancelled: {url}")


def send_intake_sms(phone, ticket, url) -> dict:
    from . import sms
    if not phone:
        return {"sent": False, "reason": "no phone number on the call"}
    r = sms.send_sms(phone, sms_text_new(ticket, url))
    return {"sent": bool(r.get("ok")), "reason": None if r.get("ok") else r.get("error")}


def expire_overdue(now_=None) -> dict:
    """Cancel phone complaints that got no photo or video within the window; remind one hour before. Idempotent."""
    from . import sms
    t = now_ or now()
    out = {"cancelled": 0, "reminded": 0}
    s = SessionLocal()
    try:
        rows = (s.query(Complaint, ComplaintMeta).join(ComplaintMeta, ComplaintMeta.complaint_id == Complaint.id)
                .filter(ComplaintMeta.source == "phone", Complaint.status == "submitted").all())
        for c, m in rows:
            if c.media:
                continue
            age_h = (t - c.created_at).total_seconds() / 3600.0
            ev = list(m.evidence or [])
            if age_h >= EVIDENCE_WINDOW_H:
                c.status = "cancelled"
                c.admin_note = (c.admin_note or "") + f" Cancelled automatically: no photo or video was added within {EVIDENCE_WINDOW_H} hours."
                c.updated_at = t
                m.evidence = ev + ["cancelled: no evidence in 6 hours"]
                s.commit()
                events.publish("complaint.updated", {"id": c.id, "ticket": c.ticket, "status": c.status, "source": "phone"})
                if c.citizen_phone:
                    sms.send_sms(c.citizen_phone, f"Disha AI: complaint {c.ticket} was cancelled because no photo or video was added within "
                                                  f"{EVIDENCE_WINDOW_H} hours. You can report the road again any time.")
                out["cancelled"] += 1
            elif age_h >= REMIND_AT_H and "reminder sent" not in ev and c.citizen_phone:
                url = f"{os.getenv('RD_PUBLIC_URL', '').rstrip('/')}/upload/{c.ticket}"
                sms.send_sms(c.citizen_phone, f"Disha AI: about 1 hour left to add a photo or video for complaint {c.ticket}, or it will be cancelled: {url}")
                m.evidence = ev + ["reminder sent"]
                s.commit()
                out["reminded"] += 1
    finally:
        s.close()
    return out


def _expiry_loop():
    while True:
        try:
            r = expire_overdue()
            if r["cancelled"] or r["reminded"]:
                print("[voice] evidence window:", r)
        except Exception as e:
            print("[voice] evidence window check failed:", repr(e))
        time.sleep(300)


# ---------- photo upload ----------
MAX_UPLOAD_FILES = 5
GPS_GOOD_M = 100.0


def _what(pot, crk):
    return ", ".join(x for x in (f"{pot} pothole{'s' if pot != 1 else ''}" if pot else "",
                                 f"{crk} crack{'s' if crk != 1 else ''}" if crk else "") if x)


def handle_upload(ticket: str, files: list, lat, lon, accuracy) -> dict:
    """files: list of (bytes, filename). GPS under 100 m accuracy replaces the spoken/geocoded location."""
    from . import main as mm
    s = SessionLocal()
    try:
        c = s.query(Complaint).filter(Complaint.ticket == ticket).first()
        if c is None:
            raise HTTPException(404, "ticket not found")
        if c.status == "cancelled":
            raise HTTPException(410, "This report was cancelled because no photo or video was added within 6 hours. "
                                     "Please call or report the road again.")
        meta = _meta_for(s, c, source="web")
        has_gps = lat is not None and lon is not None and -90 <= lat <= 90 and -180 <= lon <= 180
        if has_gps and (c.lat is None or (accuracy is not None and accuracy < GPS_GOOD_M)):
            c.lat, c.lon = lat, lon
            meta.geocode_source = "gps"
            acc = f"{int(round(accuracy))} m" if accuracy is not None else "unknown"
            _raise(meta, meta.verification, f"GPS from citizen phone, accuracy {acc}")
            s.commit()
        la, lo = (lat, lon) if has_gps else (c.lat, c.lon)
        note = f"Photo for complaint {c.ticket} ({c.category}) {c.description or ''}"[:1000]
        pot = crk = videos = stored = 0
        conf, jobs, skipped = 0.0, [], []
        for data, filename in files:
            try:
                insp, res = mm._ingest(s, data, filename, la, lo, road_name=c.address,
                                       inspector=f"citizen upload: {c.ticket}", notes=note)
            except HTTPException as e:
                s.rollback()
                skipped.append(f"{filename}: {e.detail}")
                continue
            stored += 1
            s.add(ComplaintMedia(complaint_id=c.id, inspection_id=insp.id, job_id=res.get("job_id"),
                                 media_type=insp.media_type))
            s.commit()
            if insp.media_type == "video":
                videos += 1
                jobs.append(res.get("job_id"))
                continue
            for d in (res.get("inspection") or {}).get("detections") or []:
                fc = d.get("final_class") or ""
                if fc == "pothole" or "crack" in fc:
                    pot += fc == "pothole"
                    crk += "crack" in fc
                    conf = max(conf, d.get("confidence") or 0)
        if not stored:
            raise HTTPException(400, "no file could be read. " + "; ".join(skipped))
        meta = s.get(ComplaintMeta, c.id)
        msgs = []
        if pot or crk:
            what = _what(pot, crk)
            _raise(meta, "photo_verified", f"Photo upload: AI detected {what}, max confidence {conf:.2f}")
            msgs.append(f"Our system found {what} in your photos.")
        if videos:
            _raise(meta, "photo_verified", "Photo upload: video submitted, analysis running")
            msgs.append("Your video is being analysed now.")
        if not (pot or crk or videos):
            _raise(meta, meta.verification, "Photo upload: no pothole or crack detected by AI")
            msgs.append("Your photos are saved for the field team.")
        corroborate(s, c, meta)
        c.updated_at = now()
        s.commit()
        events.publish("complaint.updated", {"id": c.id, "ticket": c.ticket, "status": c.status,
                                             "verification": meta.verification, "source": meta.source})
        return {"ok": True, "ticket": c.ticket, "verification": meta.verification, "files": stored,
                "skipped": skipped, "detections": pot + crk, "job_ids": jobs, "lat": c.lat, "lon": c.lon,
                "location_source": meta.geocode_source, "message": "Thank you. " + " ".join(msgs),
                "evidence": list(meta.evidence or [])}
    finally:
        s.close()


def _f(v):
    try:
        return float(v) if v not in (None, "", "null") else None
    except (TypeError, ValueError):
        return None


class VerifyBody(BaseModel):
    level: str = "field_verified"
    note: Optional[str] = None


class ImportBody(BaseModel):
    calls: list[dict]


def register(app):
    Base.metadata.create_all(engine, tables=[ComplaintMeta.__table__, GeocodeCache.__table__])
    threading.Thread(target=_expiry_loop, daemon=True, name="evidence-window").start()

    @app.post("/api/voice/complaint")
    async def voice_complaint(request: Request):
        """Call-end webhook from the voice agent. Accepts a flat object or a nested call payload."""
        raw = await request.body()
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except ValueError:
            form = urllib.parse.parse_qs(raw.decode("utf-8", "replace"))
            payload = {k: v[0] for k, v in form.items()}
            if not payload:
                raise HTTPException(400, "body must be JSON")
        call = extract_call(payload)
        base = _base(request)

        def work():
            s = SessionLocal()
            try:
                return create_from_call(s, call, base)
            finally:
                s.close()

        return await run_in_threadpool(work)

    @app.post("/api/voice/import")
    def voice_import(body: ImportBody, request: Request, _u=Depends(auth.require_officer)):
        base, out = _base(request), []
        s = SessionLocal()
        try:
            for i, raw in enumerate(body.calls):
                try:
                    out.append(create_from_call(s, extract_call(raw), base))
                except HTTPException as e:
                    s.rollback()
                    out.append({"index": i, "error": e.detail})
        finally:
            s.close()
        return {"created": sum(1 for r in out if r.get("ticket") and not r.get("duplicate")), "results": out}

    @app.get("/api/voice/queue", dependencies=[Depends(auth.require_officer)])
    def voice_queue(request: Request, filter: str = "needs_check", limit: int = 300):
        base = _base(request)
        s = SessionLocal()
        try:
            rows = (s.query(Complaint, ComplaintMeta).join(ComplaintMeta, ComplaintMeta.complaint_id == Complaint.id)
                    .filter(ComplaintMeta.source == "phone").order_by(Complaint.created_at.desc()).limit(limit).all())
            changed = False
            for c, m in rows:
                if m.verification in ("unverified", "corroborated"):
                    changed |= corroborate(s, c, m)
            if changed:
                s.commit()
            if filter == "needs_check":
                rows = [(c, m) for c, m in rows if _needs_check(c, m)]
            return [ser_queue(c, m, base) for c, m in rows]
        finally:
            s.close()

    @app.get("/api/voice/queue/count", dependencies=[Depends(auth.require_officer)])
    def voice_queue_count():
        s = SessionLocal()
        try:
            rows = (s.query(Complaint, ComplaintMeta).join(ComplaintMeta, ComplaintMeta.complaint_id == Complaint.id)
                    .filter(ComplaintMeta.source == "phone").all())
            return {"needs_check": sum(1 for c, m in rows if _needs_check(c, m))}
        finally:
            s.close()

    @app.post("/api/voice/verify/{complaint_id}")
    def voice_verify(complaint_id: int, body: VerifyBody, officer=Depends(auth.require_officer)):
        if body.level not in LEVELS:
            raise HTTPException(400, f"level must be one of {LEVELS}")
        s = SessionLocal()
        try:
            c = s.get(Complaint, complaint_id)
            if c is None:
                raise HTTPException(404)
            m = _meta_for(s, c)
            if RANK[body.level] < RANK.get(m.verification or "unverified", 0):
                raise HTTPException(400, f"already {m.verification}; verification is never downgraded")
            who = (officer or {}).get("full_name") or (officer or {}).get("email") or "officer"
            label = {"field_verified": "Field check", "photo_verified": "Photo checked",
                     "corroborated": "Corroborated"}.get(body.level, "Note")
            note = (body.note or "").strip()
            _raise(m, body.level, f"{label} by {who}" + (f": {note}" if note else ""))
            c.updated_at = now()
            s.commit()
            events.publish("complaint.updated", {"id": c.id, "ticket": c.ticket, "status": c.status,
                                                 "verification": m.verification, "source": m.source})
            return {"complaint_id": c.id, "ticket": c.ticket, "verification": m.verification,
                    "evidence": list(m.evidence or [])}
        finally:
            s.close()

    @app.post("/api/voice/upload/{ticket}")
    async def voice_upload(ticket: str, files: list[UploadFile] = File(default=[]),
                           file: Optional[UploadFile] = File(None), lat: Optional[str] = Form(None),
                           lon: Optional[str] = Form(None), accuracy: Optional[str] = Form(None)):
        items = [f for f in ([file] if file else []) + list(files or []) if f is not None and f.filename]
        if not items:
            raise HTTPException(400, "choose a photo or video")
        if len(items) > MAX_UPLOAD_FILES:
            raise HTTPException(400, f"max {MAX_UPLOAD_FILES} files per upload")
        payload = []
        for f in items:
            data = await f.read()
            if data:
                payload.append((data, f.filename))
        if not payload:
            raise HTTPException(400, "empty file")
        return await run_in_threadpool(handle_upload, ticket, payload, _f(lat), _f(lon), _f(accuracy))

    @app.get("/api/voice/link/{ticket}")
    def voice_link(ticket: str, request: Request):
        s = SessionLocal()
        try:
            if not s.query(Complaint.id).filter(Complaint.ticket == ticket).first():
                raise HTTPException(404, "ticket not found")
        finally:
            s.close()
        url = f"{_base(request)}/upload/{ticket}"
        return {"ticket": ticket, "upload_url": url,
                "sms_text": sms_text_new(ticket, url), "window_hours": EVIDENCE_WINDOW_H}

    @app.get("/upload/{ticket}", response_class=HTMLResponse)
    def upload_page(ticket: str):
        s = SessionLocal()
        try:
            c = s.query(Complaint).filter(Complaint.ticket == ticket).first()
            m = s.get(ComplaintMeta, c.id) if c else None
            dl = deadline_for(c, m) if c else None
            state = "cancelled" if (c and c.status == "cancelled") else ("done" if (c and c.media) else "open")
            where = (m.location_text if m else None) or (c.address if c else None) or ""
            if m and m.landmark:
                where = f"{where}, near {_clean_place(m.landmark)}" if where else f"Near {_clean_place(m.landmark)}"
        finally:
            s.close()
        page = (STATIC / "upload.html").read_text(encoding="utf-8")
        page = (page.replace("{{TICKET}}", html.escape(ticket))
                .replace("{{LOCATION}}", html.escape(where or "Location not recorded"))
                .replace("{{FOUND}}", "1" if c else "0")
                .replace("{{DEADLINE}}", (dl.isoformat() + "Z") if dl else "")
                .replace("{{STATE}}", state))
        return HTMLResponse(page, status_code=200 if c else 404)

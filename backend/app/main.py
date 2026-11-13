import json
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from . import auth, config, detector, events, live, pipeline, reports, scoring, similarity
from . import severity as severity_mod
from . import screening
from .db import (Complaint, ComplaintMedia, Defect, DefectHistory, Detection, Inspection, SessionLocal, get_session,
                 init_db, now)
from .geo import GpxTrack, haversine_m, read_exif
from . import ops
from . import voice
from . import citizen

app = FastAPI(title="RoadWatch AI", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
init_db()

app.mount("/media/uploads", StaticFiles(directory=config.UPLOADS), name="uploads")
app.mount("/media/annotated", StaticFiles(directory=config.ANNOTATED), name="annotated")
app.mount("/media/crops", StaticFiles(directory=config.CROPS), name="crops")
if (config.ROOT / "samples").exists():
    app.mount("/media/samples", StaticFiles(directory=config.ROOT / "samples"), name="samples")

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
VIDEO_EXT = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}
JOBS: dict = {}


# ---------- serializers ----------
def ser_det(d: Detection):
    return {
        "id": d.id, "inspection_id": d.inspection_id, "defect_id": d.defect_id,
        "defect_uid": d.defect.uid if d.defect else None, "class_name": d.class_name, "final_class": d.final_class,
        "confidence": d.confidence, "bbox": [d.x1, d.y1, d.x2, d.y2], "area_ratio": d.area_ratio,
        "severity": d.severity, "final_severity": d.final_severity, "severity_score": d.severity_score,
        "risk_score": d.risk_score, "risk_level": d.risk_level, "track_id": d.track_id,
        "frame_index": d.frame_index, "frames_seen": d.frames_seen, "lat": d.lat, "lon": d.lon,
        "crop_url": f"/media/crops/{d.crop_path}" if d.crop_path else None, "is_duplicate": d.is_duplicate,
        "match_score": d.match_score, "match_distance_m": d.match_distance_m, "verification": d.verification,
        "corrected_class": d.corrected_class, "corrected_severity": d.corrected_severity,
        "verified_by": d.verified_by, "verified_at": d.verified_at, "verify_note": d.verify_note,
    }


def ser_insp(i: Inspection, with_dets=False):
    out = {
        "id": i.id, "media_type": i.media_type, "original_name": i.original_name,
        "media_url": f"/media/uploads/{Path(i.stored_path).name}" if i.stored_path else None,
        "annotated_url": f"/media/annotated/{Path(i.annotated_path).name}" if i.annotated_path else None,
        "width": i.width, "height": i.height, "frames_processed": i.frames_processed, "fps": i.fps,
        "captured_at": i.captured_at, "created_at": i.created_at, "lat": i.lat, "lon": i.lon,
        "location_source": i.location_source, "road_name": i.road_name, "road_type": i.road_type,
        "traffic_level": i.traffic_level, "inspector": i.inspector, "notes": i.notes,
        "duplicate_of_inspection": i.duplicate_of_inspection, "processing_ms": i.processing_ms,
        "model_name": i.model_name, "summary": i.summary,
    }
    if with_dets:
        out["detections"] = [ser_det(d) for d in i.detections]
    return out


def ser_defect(d: Defect):
    return {
        "id": d.id, "uid": d.uid, "class_name": d.class_name, "lat": d.lat, "lon": d.lon,
        "location_source": d.location_source, "road_type": d.road_type, "traffic_level": d.traffic_level,
        "severity": d.severity, "severity_score": d.severity_score, "risk_score": d.risk_score,
        "risk_level": d.risk_level, "status": d.status, "trend": d.trend, "report_count": d.report_count,
        "crop_url": f"/media/crops/{d.best_crop}" if d.best_crop else None, "first_seen": d.first_seen,
        "last_seen": d.last_seen, "verified": d.verified,
    }


# ---------- helpers ----------
def _parse_dt(v: Optional[str]):
    if not v:
        return None
    try:
        return datetime.fromisoformat(v.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        raise HTTPException(400, f"Bad datetime: {v}")


def _f(v):
    try:
        return float(v) if v not in (None, "", "null") else None
    except ValueError:
        return None


def _resolve_location(exif, lat, lon, gpx):
    if exif.get("lat") is not None:
        return exif["lat"], exif["lon"], "exif"
    if gpx is not None:
        la, lo = gpx.position(0)
        return la, lo, "gpx"
    if lat is not None and lon is not None:
        return lat, lon, "manual"
    return None, None, "unknown"


# ---------- endpoints ----------
@app.get("/api/health")
def health():
    import torch
    try:
        info = detector.model_info()
    except Exception as e:  # noqa
        info = {"error": str(e)}
    return {"ok": True, "cuda": torch.cuda.is_available(), "model": info}


@app.post("/api/inspections")
async def create_inspection(
    file: UploadFile = File(...), gpx_file: Optional[UploadFile] = File(None), lat: Optional[str] = Form(None),
    lon: Optional[str] = Form(None), captured_at: Optional[str] = Form(None), road_name: Optional[str] = Form(None),
    road_type: str = Form("unknown"), traffic_level: str = Form("unknown"), inspector: Optional[str] = Form(None),
    notes: Optional[str] = Form(None), gpx_offset_s: float = Form(0.0), s: Session = Depends(get_session),
):
    gpx = None
    if gpx_file is not None and gpx_file.filename:
        try:
            gpx = GpxTrack.parse(await gpx_file.read())
        except Exception as e:
            raise HTTPException(400, f"Invalid GPX: {e}")
    insp, res = _ingest(s, await file.read(), file.filename, _f(lat), _f(lon), captured_at, road_name, road_type,
                        traffic_level, inspector, notes, gpx, gpx_offset_s)
    return res


def _ingest(s, data, filename, lat, lon, captured_at=None, road_name=None, road_type="unknown",
            traffic_level="unknown", inspector=None, notes=None, gpx=None, gpx_offset_s=0.0):
    """Store one media file as an Inspection and run detection (image now, video in a background job)."""
    ext = Path(filename or "").suffix.lower()
    if ext not in IMAGE_EXT | VIDEO_EXT:
        raise HTTPException(400, f"Unsupported file type {ext}")
    stored = config.UPLOADS / f"{uuid.uuid4().hex}{ext}"
    stored.write_bytes(data)
    exif = read_exif(stored) if ext in IMAGE_EXT else {"lat": None, "lon": None, "captured_at": None}
    la, lo, src = _resolve_location(exif, lat, lon, gpx)
    when = _parse_dt(captured_at) or exif.get("captured_at") or now()
    insp = Inspection(media_type="image" if ext in IMAGE_EXT else "video", original_name=filename,
                      stored_path=str(stored), captured_at=when, lat=la, lon=lo, location_source=src,
                      road_name=road_name, road_type=road_type or "unknown", traffic_level=traffic_level or "unknown",
                      inspector=inspector, notes=notes, model_name=detector.model_info()["weights"])
    s.add(insp)
    s.commit()

    if insp.media_type == "image":
        return insp, _process_image(s, insp, stored)

    job = uuid.uuid4().hex
    JOBS[job] = {"status": "running", "progress": 0.0, "inspection_id": insp.id}
    threading.Thread(target=_process_video_job, args=(job, insp.id, stored, gpx, gpx_offset_s), daemon=True).start()
    return insp, {"job_id": job, "inspection_id": insp.id, "status": "running"}


def _process_image(s, insp, stored):
    img = cv2.imdecode(np.fromfile(str(stored), dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(400, "Could not decode image")
    t0 = time.time()
    h, w = img.shape[:2]
    insp.width, insp.height = w, h
    insp.image_hash = similarity.dhash(img)
    dup = None
    for other in s.query(Inspection).filter(Inspection.id != insp.id, Inspection.image_hash != None).all():  # noqa
        if similarity.hamming(other.image_hash, insp.image_hash) <= 3:
            dup = other.id
            break
    insp.duplicate_of_inspection = dup
    rows, meta = detector.detect_image(img)
    dets = pipeline.register(s, insp, rows, frame_img=img, duplicate_upload=dup is not None)
    ann_rows = [dict(r, class_name=r["class_name"]) for r in rows]
    uids = {}
    for r, d in zip(ann_rows, dets):
        uids[id(r)] = d.defect.uid if d.defect else ""
    ann = detector.draw(img, ann_rows, lambda r: f'{uids.get(id(r), "")} {r["class_name"].replace("_", " ")} '
                                                  f'{r["confidence"]:.2f} | {r["severity"]}')
    ann_path = config.ANNOTATED / f"{Path(stored).stem}.jpg"
    cv2.imwrite(str(ann_path), ann, [cv2.IMWRITE_JPEG_QUALITY, 90])
    insp.annotated_path = str(ann_path)
    insp.processing_ms = int((time.time() - t0) * 1000)
    insp.summary = dict(pipeline.summarize(dets), enhanced=meta["enhanced"])
    s.commit()
    s.refresh(insp)
    out = ser_insp(insp, with_dets=True)
    _announce(out)
    return {"status": "done", "inspection": out}


def _announce(insp_dict):
    """Realtime: tell officer consoles about a processed inspection and any new / re-sighted defects."""
    events.publish("inspection.processed", {k: insp_dict.get(k) for k in (
        "id", "media_type", "original_name", "annotated_url", "lat", "lon", "summary", "captured_at")})
    for d in insp_dict.get("detections") or []:
        events.publish("defect.updated" if d["is_duplicate"] else "defect.created", {
            "defect_id": d["defect_id"], "uid": d["defect_uid"], "class_name": d["class_name"],
            "severity": d["severity"], "risk_score": d["risk_score"], "risk_level": d["risk_level"],
            "lat": d["lat"], "lon": d["lon"], "crop_url": d["crop_url"], "inspection_id": d["inspection_id"]})


def _process_video_job(job, insp_id, stored, gpx, gpx_offset):
    s = SessionLocal()
    try:
        insp = s.get(Inspection, insp_id)
        out = config.ANNOTATED / f"{Path(stored).stem}.mp4"

        def cb(p):
            JOBS[job]["progress"] = round(p, 3)

        tracks, meta = detector.detect_video(stored, out, cb)
        insp.width, insp.height, insp.fps = meta["width"], meta["height"], meta["fps"]
        insp.frames_processed = meta["frames_processed"]
        dets = pipeline.register(s, insp, tracks, gpx=gpx, gpx_offset=gpx_offset)
        insp.annotated_path = str(out)
        insp.processing_ms = meta["ms"]
        insp.summary = dict(pipeline.summarize(dets), raw_track_ids=meta["raw_track_ids"],
                            unique_tracks=len(tracks), frames_processed=meta["frames_processed"])
        s.commit()
        JOBS[job].update(status="done", progress=1.0)
        _announce(ser_insp(insp, with_dets=True))
    except Exception as e:  # noqa
        import traceback
        traceback.print_exc()
        JOBS[job].update(status="error", error=str(e))
    finally:
        s.close()


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str, s: Session = Depends(get_session)):
    j = JOBS.get(job_id)
    if not j:
        raise HTTPException(404, "job not found")
    out = dict(j)
    if j["status"] == "done":
        out["inspection"] = ser_insp(s.get(Inspection, j["inspection_id"]), with_dets=True)
    return out


@app.get("/api/inspections")
def list_inspections(limit: int = 200, s: Session = Depends(get_session)):
    rows = s.query(Inspection).order_by(Inspection.created_at.desc()).limit(limit).all()
    return [ser_insp(i) for i in rows]


@app.get("/api/inspections/{iid}")
def get_inspection(iid: int, s: Session = Depends(get_session)):
    i = s.get(Inspection, iid)
    if not i:
        raise HTTPException(404)
    return ser_insp(i, with_dets=True)


@app.delete("/api/inspections/{iid}")
def delete_inspection(iid: int, s: Session = Depends(get_session), _u=Depends(auth.require_officer)):
    i = s.get(Inspection, iid)
    if not i:
        raise HTTPException(404)
    s.query(DefectHistory).filter(DefectHistory.inspection_id == iid).delete()
    s.query(ComplaintMedia).filter(ComplaintMedia.inspection_id == iid).update({"inspection_id": None})
    defect_ids = {d.defect_id for d in i.detections}
    s.delete(i)
    s.flush()
    for did in defect_ids:
        d = s.get(Defect, did)
        if d and not d.detections:
            s.query(DefectHistory).filter(DefectHistory.defect_id == did).delete()
            s.delete(d)
    s.commit()
    return {"ok": True}


@app.get("/api/defects")
def list_defects(status: Optional[str] = None, risk: Optional[str] = None, cls: Optional[str] = None,
                 s: Session = Depends(get_session)):
    q = s.query(Defect)
    if status:
        q = q.filter(Defect.status == status)
    if risk:
        q = q.filter(Defect.risk_level == risk)
    if cls:
        q = q.filter(Defect.class_name == cls)
    return [ser_defect(d) for d in q.order_by(Defect.risk_score.desc()).all()]


@app.get("/api/defects/{did}")
def get_defect(did: int, s: Session = Depends(get_session)):
    d = s.get(Defect, did)
    if not d:
        raise HTTPException(404)
    hist = (s.query(DefectHistory).filter(DefectHistory.defect_id == did).order_by(DefectHistory.observed_at).all())
    return dict(ser_defect(d), detections=[ser_det(x) for x in d.detections],
                history=[{"inspection_id": h.inspection_id, "observed_at": h.observed_at, "present": h.present,
                          "area_ratio": h.area_ratio, "severity": h.severity, "severity_score": h.severity_score,
                          "risk_score": h.risk_score, "trend": h.trend} for h in hist])


class DefectPatch(BaseModel):
    status: Optional[str] = None
    road_type: Optional[str] = None
    traffic_level: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None


@app.patch("/api/defects/{did}")
def patch_defect(did: int, body: DefectPatch, s: Session = Depends(get_session), _u=Depends(auth.require_officer)):
    d = s.get(Defect, did)
    if not d:
        raise HTTPException(404)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(d, k, v)
    if body.lat is not None:
        d.location_source = "manual"
    if body.status == "repaired":
        d.trend = "repaired"
        s.add(DefectHistory(defect_id=d.id, observed_at=now(), present=False, trend="repaired", risk_score=0))
        d.risk_score, d.risk_level = 0.0, "Low"
    else:
        pipeline.refresh_defect_risk(d)
    s.commit()
    out = ser_defect(d)
    events.publish("defect.updated", out)
    return out


class Verify(BaseModel):
    action: str  # confirm | reject | correct
    corrected_class: Optional[str] = None
    corrected_severity: Optional[str] = None
    verified_by: Optional[str] = "admin"
    note: Optional[str] = None


@app.post("/api/detections/{det_id}/verify")
def verify(det_id: int, body: Verify, s: Session = Depends(get_session), officer=Depends(auth.require_officer)):
    d = s.get(Detection, det_id)
    if not d:
        raise HTTPException(404)
    if body.action not in ("confirm", "reject", "correct", "reset"):
        raise HTTPException(400, "action must be confirm | reject | correct | reset")
    if body.action == "correct" and not (body.corrected_class or body.corrected_severity):
        raise HTTPException(400, "correction needs a class or severity")
    if body.corrected_class and body.corrected_class not in config.CLASSES:
        raise HTTPException(400, f"class must be one of {config.CLASSES}")
    if body.corrected_severity and body.corrected_severity not in severity_mod.LEVEL_RANK:
        raise HTTPException(400, f"severity must be one of {severity_mod.LEVELS}")
    d.verification = {"confirm": "confirmed", "reject": "rejected", "correct": "corrected", "reset": "pending"}[body.action]
    d.corrected_class = body.corrected_class if body.action == "correct" else None
    d.corrected_severity = body.corrected_severity if body.action == "correct" else None
    who = (officer or {}).get("full_name") or (officer or {}).get("email") or body.verified_by
    d.verified_by, d.verified_at, d.verify_note = who, now(), body.note
    defect = d.defect
    if defect:
        live = [x for x in defect.detections if x.verification != "rejected"]
        if not live:
            defect.status, defect.verified = "rejected", True
        else:
            if defect.status == "rejected":
                defect.status = "active"
            defect.verified = any(x.verification in ("confirmed", "corrected") for x in live)
            latest = max(live, key=lambda x: (x.inspection.captured_at or x.created_at, x.id))
            defect.class_name = latest.final_class
            if latest.corrected_severity:
                defect.severity = latest.corrected_severity
                defect.severity_score = severity_mod.LEVEL_SCORE[latest.corrected_severity]
            pipeline.refresh_defect_risk(defect)
            d.risk_score, d.risk_level = scoring.risk(d.final_class, defect.severity_score, defect.road_type,
                                                      defect.traffic_level, defect.report_count, defect.trend)
    s.commit()
    out = ser_det(d)
    events.publish("detection.verified", {"detection_id": d.id, "uid": out["defect_uid"],
                                          "verification": d.verification, "by": d.verified_by})
    return out


@app.get("/api/verification/queue")
def verification_queue(status: str = "pending", limit: int = 200, s: Session = Depends(get_session)):
    q = s.query(Detection)
    if status != "all":
        q = q.filter(Detection.verification == status)
    rows = q.order_by(Detection.risk_score.desc(), Detection.id.desc()).limit(limit).all()
    return [dict(ser_det(d), annotated_url=ser_insp(d.inspection)["annotated_url"],
                 media_type=d.inspection.media_type) for d in rows]


@app.get("/api/training/export")
def export_verified(s: Session = Depends(get_session), _u=Depends(auth.require_officer)):
    """Verified labels in YOLO format (zip) for future fine-tuning."""
    return Response(reports.export_yolo_zip(s), media_type="application/zip",
                    headers={"Content-Disposition": "attachment; filename=verified_labels_yolo.zip"})


@app.get("/api/stats")
def stats(s: Session = Depends(get_session)):
    defects = s.query(Defect).filter(Defect.status != "rejected").all()
    insps = s.query(Inspection).all()
    dets = s.query(Detection).all()
    by = lambda items, key: {k: sum(1 for x in items if key(x) == k) for k in sorted({key(x) for x in items})}
    timeline = {}
    for i in insps:
        day = (i.captured_at or i.created_at).date().isoformat()
        t = timeline.setdefault(day, {"date": day, "inspections": 0, "detections": 0})
        t["inspections"] += 1
        t["detections"] += len(i.detections)
    return {
        "inspections": len(insps), "images": sum(1 for i in insps if i.media_type == "image"),
        "videos": sum(1 for i in insps if i.media_type == "video"), "detections": len(dets),
        "unique_defects": len(defects), "active": sum(1 for d in defects if d.status == "active"),
        "repaired": sum(1 for d in defects if d.status == "repaired"),
        "high_risk": sum(1 for d in defects if d.risk_level == "High" and d.status == "active"),
        "duplicates_prevented": sum(1 for d in dets if d.is_duplicate),
        "pending_verification": sum(1 for d in dets if d.verification == "pending"),
        "verified": sum(1 for d in dets if d.verification in ("confirmed", "corrected")),
        "rejected": sum(1 for d in dets if d.verification == "rejected"),
        "by_class": by(defects, lambda d: d.class_name), "by_severity": by(defects, lambda d: d.severity),
        "by_risk": by(defects, lambda d: d.risk_level), "by_trend": by(defects, lambda d: d.trend),
        "timeline": sorted(timeline.values(), key=lambda x: x["date"]),
    }


@app.get("/api/progress")
def progress(lat: float, lon: float, radius_m: float = 50, s: Session = Depends(get_session)):
    """Compare all inspections around a location over time: worsening / improving / repaired."""
    insps = [i for i in s.query(Inspection).filter(Inspection.lat != None).all()  # noqa
             if haversine_m(lat, lon, i.lat, i.lon) <= radius_m]
    insps.sort(key=lambda i: i.captured_at or i.created_at)
    snaps = []
    for i in insps:
        live = [d for d in i.detections if d.verification != "rejected"]
        snaps.append({"inspection_id": i.id, "date": i.captured_at, "count": len(live),
                      "total_area": round(sum(d.area_ratio or 0 for d in live), 5),
                      "mean_severity": round(float(np.mean([d.severity_score for d in live])) if live else 0, 3),
                      "max_risk": max([d.risk_score for d in live], default=0),
                      "annotated_url": ser_insp(i)["annotated_url"]})
    verdict = "insufficient_data"
    if len(snaps) >= 2:
        a, b = snaps[0], snaps[-1]
        if b["count"] == 0 and a["count"] > 0:
            verdict = "repaired"
        elif b["total_area"] > a["total_area"] * 1.15 or b["count"] > a["count"]:
            verdict = "worsening"
        elif b["total_area"] < a["total_area"] * 0.85 or b["count"] < a["count"]:
            verdict = "improving"
        else:
            verdict = "unchanged"
    defects = [ser_defect(d) for d in s.query(Defect).filter(Defect.lat != None).all()  # noqa
               if haversine_m(lat, lon, d.lat, d.lon) <= radius_m]
    return {"verdict": verdict, "snapshots": snaps, "defects": defects}


@app.get("/api/reports/defects.csv")
def report_csv(s: Session = Depends(get_session)):
    return Response(reports.defects_csv(s), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=road_damage_report.csv"})


@app.get("/api/reports/summary.pdf")
def report_pdf(s: Session = Depends(get_session)):
    return Response(reports.summary_pdf(s, stats(s)), media_type="application/pdf",
                    headers={"Content-Disposition": "attachment; filename=road_damage_report.pdf"})


@app.get("/api/reports/inspection/{iid}.pdf")
def report_inspection_pdf(iid: int, s: Session = Depends(get_session)):
    i = s.get(Inspection, iid)
    if not i:
        raise HTTPException(404)
    return Response(reports.inspection_pdf(i), media_type="application/pdf",
                    headers={"Content-Disposition": f"attachment; filename=inspection_{iid}.pdf"})


@app.get("/api/model/metrics")
def model_metrics():
    p = config.ROOT / "models" / "metrics.json"
    if not p.exists():
        return {"available": False}
    return dict(json.loads(p.read_text()), available=True)


@app.get("/api/model/confusion_matrix.png")
def confusion_png():
    p = config.ROOT / "models" / "confusion_matrix.png"
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p)


@app.get("/api/config")
def get_config():
    return {"classes": config.CLASSES, "class_labels": config.CLASS_LABELS, "risk_method": scoring.RISK_METHOD,
            "dup_radius_m": config.DUP_RADIUS_M, "dup_similarity": config.DUP_SIM_THRESHOLD,
            "conf_threshold": config.CONF_THRESHOLD}


@app.post("/api/model/reload")
def model_reload(_u=Depends(auth.require_admin)):
    return detector.reload_model()


# ---------- citizen complaints (mobile app) ----------
COMPLAINT_CATEGORIES = ("pothole", "crack", "waterlogging", "broken_road", "other")
COMPLAINT_STATUSES = ("submitted", "in_review", "in_progress", "resolved", "rejected")
MAX_COMPLAINT_FILES = 8


def ser_complaint(c: Complaint):
    media, findings = [], []
    for m in c.media:
        i = m.inspection
        item = {"id": m.id, "media_type": m.media_type, "inspection_id": m.inspection_id, "status": "missing"}
        if i is not None:
            si = ser_insp(i)
            job = JOBS.get(m.job_id) if m.job_id else None
            if job and job["status"] != "done":
                item["status"] = job["status"]
                item["progress"] = job.get("progress", 0)
            else:
                item["status"] = "done" if i.annotated_path else "stored"
            item.update(media_url=si["media_url"], annotated_url=si["annotated_url"])
            for d in i.detections:
                if d.verification == "rejected":
                    continue
                findings.append({"class_name": d.final_class, "severity": d.final_severity,
                                 "confidence": round(d.confidence or 0, 3), "risk_level": d.risk_level,
                                 "defect_uid": d.defect.uid if d.defect else None,
                                 "crop_url": ser_det(d)["crop_url"]})
        media.append(item)
    return {
        "id": c.id, "ticket": c.ticket, "category": c.category, "description": c.description,
        "citizen_name": c.citizen_name, "citizen_phone": c.citizen_phone, "lat": c.lat, "lon": c.lon,
        "address": c.address, "status": c.status, "admin_note": c.admin_note, "created_at": c.created_at,
        "updated_at": c.updated_at, "media": media, "findings": findings,
    }


@app.post("/api/complaints")
async def create_complaint(
    category: str = Form("pothole"), description: str = Form(""), citizen_name: Optional[str] = Form(None),
    citizen_phone: Optional[str] = Form(None), device_id: Optional[str] = Form(None), lat: Optional[str] = Form(None),
    lon: Optional[str] = Form(None), address: Optional[str] = Form(None),
    files: list[UploadFile] = File(default=[]), s: Session = Depends(get_session),
    user: Optional[dict] = Depends(auth.optional_user), screening_tokens: Optional[str] = Form(None),
):
    """Anonymous filing works; when signed in the complaint is linked to the citizen's account.
    Every photo/video must show road damage (pre-checked via /api/screening/check, or screened here)."""
    if category not in COMPLAINT_CATEGORIES:
        raise HTTPException(400, f"category must be one of {COMPLAINT_CATEGORIES}")
    files = [f for f in files if f is not None and f.filename]
    if not description.strip() and not files:
        raise HTTPException(400, "add a description or at least one photo/video")
    if len(files) > MAX_COMPLAINT_FILES:
        raise HTTPException(400, f"max {MAX_COMPLAINT_FILES} files per complaint")
    # Phones send odd names (no extension, .heic, content:// leftovers). Infer the extension from the
    # content type when missing; skip formats we cannot decode instead of rejecting the whole complaint.
    usable, skipped = [], []
    for f in files:
        ext = Path(f.filename).suffix.lower()
        ctype = (f.content_type or "").lower()
        if not ext:
            ext = ".mp4" if ctype.startswith("video/") else (".jpg" if ctype.startswith("image/") else "")
            f.filename = f"{f.filename}{ext}"
        if ext in IMAGE_EXT | VIDEO_EXT:
            usable.append(f)
        else:
            skipped.append(f.filename)
    if skipped:
        print(f"complaint upload: skipped unsupported files {skipped}")
    files = usable
    if not description.strip() and not files:
        raise HTTPException(400, "These files can't be read. Use JPG or PNG photos, or MP4 / MOV videos.")
    # screening gate: refuse media without visible road damage before anything is stored
    blobs = []
    for f in files:
        blobs.append((f.filename, await f.read()))
        await f.seek(0)
    check_ids = []
    if blobs:
        import asyncio
        toks = [t.strip() for t in (screening_tokens or "").split(",") if t.strip()]
        check_ids = await asyncio.to_thread(screening.enforce, blobs, toks, device_id,
                                            citizen_phone or (user or {}).get("phone"), (user or {}).get("id"))
    la, lo = _f(lat), _f(lon)
    if user:
        citizen_name = citizen_name or user.get("full_name")
        citizen_phone = citizen_phone or user.get("phone")
    c = Complaint(category=category, description=description.strip(), citizen_name=citizen_name,
                  citizen_phone=citizen_phone, device_id=device_id, lat=la, lon=lo, address=address,
                  citizen_user_id=user["id"] if user else None)
    s.add(c)
    s.commit()
    c.ticket = f"RW-{c.id:06d}"
    s.commit()
    who = "citizen: " + (citizen_name or citizen_phone or "anonymous")
    note = f"Complaint {c.ticket} ({category}) {description.strip()}"[:1000]
    for f in files:
        data = await f.read()
        try:
            insp, res = _ingest(s, data, f.filename, la, lo, road_name=address, inspector=who, notes=note)
        except HTTPException as e:  # undecodable media: keep the complaint, skip analysis for this file
            print(f"complaint {c.ticket}: media {f.filename} skipped: {e.detail}")
            s.rollback()
            continue
        s.add(ComplaintMedia(complaint_id=c.id, inspection_id=insp.id, job_id=res.get("job_id"),
                             media_type=insp.media_type))
        s.commit()
    s.refresh(c)
    screening.link(check_ids, c.id)
    out = ser_complaint(c)
    events.publish("complaint.created", out)
    return out


def _is_officer(user):
    return (not config.AUTH_REQUIRED) or (user is not None and auth.RANK.get(user["role"], 0) >= auth.RANK["officer"])


def _owns(c: Complaint, user, device_id):
    if user and c.citizen_user_id and c.citizen_user_id == user["id"]:
        return True
    return bool(device_id) and c.device_id == device_id and c.citizen_user_id is None


@app.get("/api/complaints")
def list_complaints(phone: Optional[str] = None, device_id: Optional[str] = None, status: Optional[str] = None,
                    limit: int = 200, s: Session = Depends(get_session),
                    user: Optional[dict] = Depends(auth.optional_user)):
    """Officers see all complaints. A signed-in citizen sees their own (plus anonymous ones filed from this device);
    an anonymous caller only sees complaints filed from its device_id."""
    from sqlalchemy import and_, or_
    q = s.query(Complaint)
    if _is_officer(user):
        if phone:
            q = q.filter(Complaint.citizen_phone == phone)
        if device_id:
            q = q.filter(Complaint.device_id == device_id)
    else:
        mine = []
        if user:
            mine.append(Complaint.citizen_user_id == user["id"])
        if device_id:
            mine.append(and_(Complaint.device_id == device_id, Complaint.citizen_user_id.is_(None)))
        if not mine:
            raise HTTPException(401, "Sign in or pass device_id")
        q = q.filter(or_(*mine))
    if status:
        q = q.filter(Complaint.status == status)
    return [ser_complaint(c) for c in q.order_by(Complaint.created_at.desc()).limit(limit).all()]


@app.get("/api/complaints/{cid}")
def get_complaint(cid: int, device_id: Optional[str] = None, s: Session = Depends(get_session),
                  user: Optional[dict] = Depends(auth.optional_user)):
    c = s.get(Complaint, cid)
    if not c or not (_is_officer(user) or _owns(c, user, device_id)):
        raise HTTPException(404)
    return ser_complaint(c)


class ComplaintPatch(BaseModel):
    status: Optional[str] = None
    admin_note: Optional[str] = None


@app.patch("/api/complaints/{cid}")
def patch_complaint(cid: int, body: ComplaintPatch, s: Session = Depends(get_session),
                    _u=Depends(auth.require_officer)):
    c = s.get(Complaint, cid)
    if not c:
        raise HTTPException(404)
    if body.status is not None:
        if body.status not in COMPLAINT_STATUSES:
            raise HTTPException(400, f"status must be one of {COMPLAINT_STATUSES}")
        c.status = body.status
    if body.admin_note is not None:
        c.admin_note = body.admin_note
    c.updated_at = now()
    s.commit()
    out = ser_complaint(c)
    events.publish("complaint.updated", out,
                   audience=f"user:{c.citizen_user_id}" if c.citizen_user_id else "officer")
    return out


@app.get("/api/citizen/config")
def citizen_config():
    return {"helpline": config.HELPLINE_NUMBER, "categories": COMPLAINT_CATEGORIES,
            "max_files": MAX_COMPLAINT_FILES}


live.register_ws(app)
auth.register_routes(app)
events.register(app)
screening.register(app)
citizen.register(app)
voice.register(app)
ops.register(app)

# serve built frontend if present
_dist = config.ROOT / "frontend" / "dist"
if _dist.exists():
    app.mount("/", StaticFiles(directory=_dist, html=True), name="spa")

"""Inspection pipeline: detections -> location -> duplicate matching -> defect registry -> progress -> risk."""
import uuid
from datetime import datetime

import cv2
import numpy as np

from . import config, scoring, similarity
from .db import Defect, DefectHistory, Detection, Inspection, now
from .geo import haversine_m

UID_PREFIX = {"pothole": "PH", "alligator_crack": "AC", "transverse_crack": "TC", "longitudinal_crack": "LC",
              "manhole": "MH", "speed_breaker": "SB", "debris": "DB", "barricade": "BR"}
CRACK_FAMILY = {"alligator_crack", "transverse_crack", "longitudinal_crack"}


def compatible(a, b):
    return a == b or (a in CRACK_FAMILY and b in CRACK_FAMILY)


def save_crop(img):
    name = f"{uuid.uuid4().hex}.jpg"
    cv2.imwrite(str(config.CROPS / name), img, [cv2.IMWRITE_JPEG_QUALITY, 88])
    return name


def _radius(src_a, src_b):
    return config.DUP_RADIUS_MANUAL_M if "manual" in (src_a, src_b) else config.DUP_RADIUS_M


def find_match(s, cls, lat, lon, loc_src, emb, exclude_ids, before: datetime):
    """Best existing defect for a new detection, or (None, sim, dist).

    With location on both sides: candidate must be within the radius and visually similar (sim >= threshold);
    score = 0.6*sim + 0.4*(1 - d/radius).
    Without location: only a very high visual similarity counts (sim >= DUP_SIM_NO_GPS).
    """
    best, best_score, best_sim, best_d = None, -1.0, None, None
    q = s.query(Defect).filter(Defect.status != "rejected")
    if lat is not None:
        dlat = 0.0005  # ~55 m prefilter box
        q = q.filter((Defect.lat == None) | ((Defect.lat.between(lat - dlat, lat + dlat)) &  # noqa: E711
                                             (Defect.lon.between(lon - dlat * 2, lon + dlat * 2))))
    for d in q.all():
        if d.id in exclude_ids or not compatible(cls, d.class_name) or d.embedding is None:
            continue
        ref = similarity.from_bytes(d.embedding)
        if ref.shape != emb.shape:
            continue
        sim = similarity.cosine(emb, ref)
        if lat is not None and d.lat is not None:
            r = _radius(loc_src, d.location_source)
            dist = haversine_m(lat, lon, d.lat, d.lon)
            if dist > r or sim < config.DUP_SIM_THRESHOLD:
                continue
            score = 0.6 * sim + 0.4 * (1 - dist / r)
        else:
            dist = None
            if sim < config.DUP_SIM_NO_GPS:
                continue
            score = sim
        if score > best_score:
            best, best_score, best_sim, best_d = d, score, sim, dist
    return best, best_sim, best_d


def trend_between(prev_score, new_score, prev_sev, new_sev):
    from .severity import LEVEL_RANK as order
    if prev_score is None:
        return "new"
    if order.get(new_sev, 0) > order.get(prev_sev, 0) or new_score > prev_score * 1.15 + 0.02:
        return "worsening"
    if order.get(new_sev, 0) < order.get(prev_sev, 0) or new_score < prev_score * 0.85 - 0.02:
        return "improving"
    return "stable"


def refresh_defect_risk(d: Defect):
    d.risk_score, d.risk_level = scoring.risk(d.class_name, d.severity_score or 0, d.road_type, d.traffic_level,
                                              d.report_count, d.trend)


def register(s, insp: Inspection, rows, frame_img=None, gpx=None, gpx_offset=0.0, duplicate_upload=False):
    """Persist detections of an inspection and link each to a unique defect (new or existing)."""
    matched_ids = set()
    det_objs = []
    when = insp.captured_at or now()
    for r in rows:
        c = r.get("crop")
        if c is None and frame_img is not None:
            from .detector import crop
            c = crop(frame_img, r)
        emb = similarity.embed(c)
        crop_name = save_crop(c)

        lat, lon, src = insp.lat, insp.lon, insp.location_source
        if gpx is not None and r.get("time_s") is not None:
            lat, lon = gpx.position(r["time_s"], gpx_offset)
            src = "gpx"

        det = Detection(inspection_id=insp.id, class_name=r["class_name"], confidence=r["confidence"],
                        x1=r["x1"], y1=r["y1"], x2=r["x2"], y2=r["y2"], area_ratio=r["area_ratio"],
                        severity=r["severity"], severity_score=r["severity_score"], track_id=r.get("track_id"),
                        frame_index=r.get("frame_index", 0), frames_seen=r.get("frames_seen", 1), lat=lat, lon=lon,
                        crop_path=crop_name)

        match, sim, dist = find_match(s, r["class_name"], lat, lon, src, emb, matched_ids, when)
        if match is not None:
            matched_ids.add(match.id)
            prev = (s.query(DefectHistory).filter(DefectHistory.defect_id == match.id, DefectHistory.present == True)  # noqa
                    .order_by(DefectHistory.observed_at.desc()).first())
            tr = trend_between(prev.severity_score if prev else match.severity_score, r["severity_score"],
                               prev.severity if prev else match.severity, r["severity"])
            det.is_duplicate = True
            det.defect_id = match.id
            det.match_score = round(sim, 4) if sim is not None else None
            det.match_distance_m = round(dist, 2) if dist is not None else None
            if not duplicate_upload:
                match.report_count = (match.report_count or 1) + 1
            if when >= (match.last_seen or when):
                match.last_seen = when
                match.severity, match.severity_score = r["severity"], r["severity_score"]
                match.trend = tr
                match.status = "active" if match.status == "repaired" else match.status
            # running average embedding keeps the defect appearance up to date
            old = similarity.from_bytes(match.embedding)
            newv = old * 0.7 + emb * 0.3
            match.embedding = similarity.to_bytes(newv / (np.linalg.norm(newv) + 1e-9))
            if match.lat is None and lat is not None:
                match.lat, match.lon, match.location_source = lat, lon, src
            if insp.road_type != "unknown":
                match.road_type = insp.road_type
            if insp.traffic_level != "unknown":
                match.traffic_level = insp.traffic_level
            refresh_defect_risk(match)
            defect = match
        else:
            defect = Defect(class_name=r["class_name"], lat=lat, lon=lon, location_source=src,
                            road_type=insp.road_type, traffic_level=insp.traffic_level, severity=r["severity"],
                            severity_score=r["severity_score"], embedding=similarity.to_bytes(emb),
                            best_crop=crop_name, first_seen=when, last_seen=when, trend="new", report_count=1)
            refresh_defect_risk(defect)
            s.add(defect)
            s.flush()
            defect.uid = f"{UID_PREFIX.get(defect.class_name, 'RD')}-{defect.id:05d}"
            matched_ids.add(defect.id)
            det.defect_id = defect.id

        det.risk_score, det.risk_level = scoring.risk(r["class_name"], r["severity_score"], insp.road_type,
                                                      insp.traffic_level, defect.report_count, defect.trend,
                                                      lane=r.get("lane"))
        s.add(det)
        s.add(DefectHistory(defect_id=defect.id, inspection_id=insp.id, observed_at=when, present=True,
                            area_ratio=r["area_ratio"], severity=r["severity"], severity_score=r["severity_score"],
                            risk_score=det.risk_score, trend=defect.trend))
        det_objs.append(det)

    if not duplicate_upload:
        mark_repaired(s, insp, matched_ids, when)
    s.flush()
    return det_objs


def mark_repaired(s, insp, matched_ids, when):
    """Defects near this (newer) inspection's location that were not observed again are flagged as repaired.

    Only applied for image inspections with a device location (EXIF / GPX), where the camera footprint
    reasonably covers the recorded location. Manual pins are too coarse to conclude a repair; the admin can
    mark those repaired from the registry.
    """
    if insp.media_type != "image" or insp.lat is None or insp.location_source not in ("exif", "gpx"):
        return
    r = config.REPAIR_RADIUS_M
    dlat = 0.0003
    near = (s.query(Defect).filter(Defect.status == "active", Defect.lat.between(insp.lat - dlat, insp.lat + dlat),
                                   Defect.lon.between(insp.lon - dlat * 2, insp.lon + dlat * 2)).all())
    for d in near:
        if d.id in matched_ids or d.lat is None:
            continue
        if haversine_m(insp.lat, insp.lon, d.lat, d.lon) > r or (d.last_seen and d.last_seen >= when):
            continue
        d.status, d.trend = "repaired", "repaired"
        d.severity_score = 0.0
        refresh_defect_risk(d)
        d.risk_score, d.risk_level = 0.0, "Low"
        s.add(DefectHistory(defect_id=d.id, inspection_id=insp.id, observed_at=when, present=False,
                            trend="repaired", risk_score=0.0))


def summarize(dets):
    by_class, by_sev, by_risk = {}, {}, {}
    for d in dets:
        by_class[d.class_name] = by_class.get(d.class_name, 0) + 1
        by_sev[d.severity] = by_sev.get(d.severity, 0) + 1
        by_risk[d.risk_level] = by_risk.get(d.risk_level, 0) + 1
    return {"total": len(dets), "new_defects": sum(1 for d in dets if not d.is_duplicate),
            "duplicates": sum(1 for d in dets if d.is_duplicate), "by_class": by_class, "by_severity": by_sev,
            "by_risk": by_risk, "max_risk": max([d.risk_score for d in dets], default=0)}

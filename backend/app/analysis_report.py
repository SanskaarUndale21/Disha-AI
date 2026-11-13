"""Full analysis PDF for one inspection (image or video).

GET /api/reports/analysis/{inspection_id}.pdf
"""
import io
import os
from collections import Counter
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import Response

from . import config
from .db import Inspection, SessionLocal
from .reports import _qr, _table, _fmt_dt, road_record_flowables

ASPHALT = "#17191d"
YELLOW = "#f2b705"
HIGH_CONF = 0.40


def _video_frames(path, n_extra=4):
    """Middle frame first, then up to n_extra evenly spaced others. Returns list of (label, jpeg bytes)."""
    import cv2
    cap = cv2.VideoCapture(str(path))
    try:
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if total <= 0:
            return []
        picks = [total // 2]
        for k in range(1, n_extra + 1):
            idx = int(total * k / (n_extra + 1))
            if all(abs(idx - p) > max(1, total // 50) for p in picks):
                picks.append(idx)
        out = []
        for idx in picks:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ok, fr = cap.read()
            if not ok:
                continue
            h, w = fr.shape[:2]
            if w > 960:
                fr = cv2.resize(fr, (960, int(h * 960 / w)))
            ok, buf = cv2.imencode(".jpg", fr, [cv2.IMWRITE_JPEG_QUALITY, 85])
            if ok:
                out.append((f"Frame {idx} of {total}", buf.tobytes()))
        return out
    finally:
        cap.release()


def _fit(src, w, h):
    """reportlab Image from a path or bytes, scaled to fit within w x h."""
    from reportlab.platypus import Image as RLImage
    import cv2
    import numpy as np
    try:
        if isinstance(src, (bytes, bytearray)):
            im = cv2.imdecode(np.frombuffer(src, np.uint8), cv2.IMREAD_COLOR)
            ref = io.BytesIO(bytes(src))
        else:
            im = cv2.imread(str(src))
            ref = str(src)
        ih, iw = im.shape[:2]
    except Exception:
        return None
    k = min(w / iw, h / ih)
    return RLImage(ref, width=iw * k, height=ih * k)


def _footer(canvas, doc):
    from reportlab.lib import colors
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor(YELLOW))
    canvas.setLineWidth(1.2)
    canvas.line(36, 30, doc.pagesize[0] - 36, 30)
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(colors.HexColor("#4b5563"))
    canvas.drawString(36, 19, "Disha AI | AI-assisted road damage analysis | Detections may contain errors")
    canvas.drawRightString(doc.pagesize[0] - 36, 19, f"Page {doc.page}")
    canvas.restoreState()


def build_pdf(s, i: Inspection, base: str) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import (HRFlowable, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table,
                                    TableStyle)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, title=f"Road Damage Analysis Report, inspection {i.id}",
                            leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=44)
    ss = getSampleStyleSheet()
    small = ParagraphStyle("small", parent=ss["BodyText"], fontSize=7.5, leading=9, alignment=TA_LEFT)
    cell = ParagraphStyle("cell", parent=ss["BodyText"], fontSize=8, leading=10)
    white_title = ParagraphStyle("wt", parent=ss["Title"], textColor=colors.white, alignment=TA_LEFT, fontSize=20,
                                 leading=24, spaceAfter=2)
    white_sub = ParagraphStyle("ws", parent=ss["Normal"], textColor=colors.HexColor(YELLOW), fontSize=9)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], fontSize=12, spaceBefore=10, spaceAfter=4,
                        textColor=colors.HexColor(ASPHALT))

    dets = sorted(i.detections, key=lambda d: (-(d.risk_score or 0), d.id))
    is_video = i.media_type == "video"
    loc = f"{i.lat:.6f}, {i.lon:.6f}" if i.lat is not None and i.lon is not None else "not recorded"
    size = (f"{i.frames_processed} frames processed" + (f" at {i.fps:.1f} fps" if i.fps else "")
            + (f", {i.width} x {i.height} px" if i.width else "")) if is_video else \
        f"{i.width} x {i.height} px"

    # cover title bar
    bar = Table([[[Paragraph("Road Damage Analysis Report", white_title),
                   Paragraph(f"Inspection #{i.id} | {i.original_name or '-'}", white_sub)],
                  _qr(f"{base}/map", 70)]], colWidths=[14 * cm, 3.6 * cm])
    bar.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(ASPHALT)),
                             ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 12),
                             ("TOPPADDING", (0, 0), (-1, -1), 10), ("BOTTOMPADDING", (0, 0), (-1, -1), 10)]))
    el = [bar, HRFlowable(width="100%", thickness=3, color=colors.HexColor(YELLOW), spaceBefore=0, spaceAfter=8)]

    secs = [["Field", "Value"],
            ["Inspection ID", f"#{i.id} ({i.media_type})"],
            ["File name", Paragraph(i.original_name or "-", cell)],
            ["Captured", _fmt_dt(i.captured_at, "%d %b %Y %H:%M")],
            ["Analysed on", _fmt_dt(i.created_at, "%d %b %Y %H:%M")],
            ["Model weights", i.model_name or "not recorded"],
            ["Frames / image size", size],
            ["Processing time", f"{(i.processing_ms or 0) / 1000:.1f} s" if i.processing_ms else "-"],
            ["Location (source)", f"{loc} ({i.location_source or 'unknown'})" + (f"; {i.address}" if i.address else "")],
            ["Road", f"{i.road_name or '-'} | type {i.road_type or 'unknown'} | traffic {i.traffic_level or 'unknown'}"],
            ["Inspector", i.inspector or "-"]]
    el += [_table(secs, widths=[130, 400])]

    # images
    el.append(Paragraph("Annotated result", h2))
    shown = False
    ann = i.annotated_path if i.annotated_path and Path(i.annotated_path).exists() else None
    if not is_video:
        src = ann or (i.stored_path if i.stored_path and Path(i.stored_path).exists() else None)
        im = _fit(src, 17.5 * cm, 12 * cm) if src else None
        if im:
            el += [im]
            shown = True
    else:
        frames = []
        for p in (ann, i.stored_path):
            if p and Path(p).exists():
                try:
                    frames = _video_frames(p)
                except Exception:
                    frames = []
                if frames:
                    break
        if frames:
            main_im = _fit(frames[0][1], 17.5 * cm, 10.5 * cm)
            if main_im:
                el += [main_im, Paragraph(f"Middle frame ({frames[0][0]})", small)]
                shown = True
            rest = [(lab, _fit(b, 8.6 * cm, 5.5 * cm), ) for lab, b in frames[1:]]
            rest = [(lab, im) for lab, im in rest if im]
            if rest:
                cells = [[im, Paragraph(lab, small)] for lab, im in rest]
                rows = []
                for k in range(0, len(cells), 2):
                    pair = cells[k:k + 2]
                    rows.append([c[0] for c in pair] + [""] * (2 - len(pair)))
                    rows.append([c[1] for c in pair] + [""] * (2 - len(pair)))
                g = Table(rows, colWidths=[8.8 * cm, 8.8 * cm])
                g.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
                el += [Spacer(1, 4), g]
    if not shown:
        el.append(Paragraph("Annotated media is not available on this server.", ss["BodyText"]))

    # summary
    new = [d for d in dets if not d.is_duplicate]
    dup = [d for d in dets if d.is_duplicate]
    defect_ids = {d.defect_id for d in dets if d.defect_id}
    by_class = Counter((d.final_class or "-").replace("_", " ") for d in dets)
    by_sev = Counter(d.final_severity or "-" for d in dets)
    high = [d for d in dets if (d.risk_level or "").lower() == "high"]
    maxrisk = max([d.risk_score or 0 for d in dets], default=0)
    el.append(Paragraph("Summary", h2))
    srows = [["Measure", "Value"],
             ["Total detections", str(len(dets))],
             ["New (first report)", str(len(new))],
             ["Already reported (duplicates)", str(len(dup))],
             ["Unique defects", str(len(defect_ids))],
             ["By class", ", ".join(f"{k}: {v}" for k, v in by_class.most_common()) or "none"],
             ["By severity", ", ".join(f"{k}: {v}" for k, v in by_sev.most_common()) or "none"],
             ["High-risk detections", str(len(high))],
             ["Highest risk score", f"{maxrisk:.0f} / 100"]]
    # repair cost (optional)
    try:
        from .ops import estimate
        seen, total, n = set(), 0, 0
        for d in dets:
            if d.defect is not None and d.defect.id not in seen:
                seen.add(d.defect.id)
                c = estimate(d.defect)
                if c:
                    total += c["total_cost"]
                    n += 1
        if n:
            srows.append(["Repair cost estimate", f"Rs {total:,} for {n} defect(s), planning assumptions"])
    except Exception:
        pass
    el.append(_table(srows, widths=[160, 370]))

    # defect table
    el.append(Paragraph("Detections", h2))
    head = ["Defect", "Class", "Conf.", "Confidence band", "Severity", "Risk"] + (["Track / frames"] if is_video else []) \
        + ["Crop"]
    rows = [head]
    for d in dets:
        crop = None
        if d.crop_path and (config.CROPS / d.crop_path).exists():
            crop = _fit(config.CROPS / d.crop_path, 3 * cm, 3 * cm)
        r = [d.defect.uid if d.defect else "-", Paragraph((d.final_class or "-").replace("_", " "), cell),
             f"{d.confidence:.2f}", "high confidence" if (d.confidence or 0) >= HIGH_CONF else "possible",
             d.final_severity or "-", f"{(d.risk_score or 0):.0f} ({d.risk_level or '-'})"]
        if is_video:
            r.append(f"{d.track_id if d.track_id is not None else '-'} / {d.frames_seen or 1}")
        r.append(crop or "-")
        rows.append(r)
    if len(rows) == 1:
        el.append(Paragraph("No road damage was detected in this inspection.", ss["BodyText"]))
    else:
        widths = [50, 70, 35, 70, 48, 60] + ([55] if is_video else []) + [90]
        widths[-1] = 530 - sum(widths[:-1])
        t = _table(rows, widths=widths)
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
        el.append(t)

    # road record
    el += road_record_flowables(i.lat, i.lon, ss)

    # methods
    el.append(Paragraph("Methods and limits", h2))
    el.append(Paragraph(
        "Damage is detected by a computer-vision model and every result can contain errors, including missed "
        "damage and false alarms. The confidence value is the model's own score and is not a probability of being "
        "correct. On held-out road photos, detections at confidence 0.40 and above were confirmed with about 87% "
        "precision, so detections below 0.40 are marked as possible and should be checked by a person. Severity, "
        "risk score and repair cost are estimates built on stated assumptions. Dates are the capture time stored "
        "with the file, or the upload time when none was available. Locations come from photo GPS, a GPS track or "
        "a manual pin and are accurate to several metres. Repair cost and road record figures are for planning "
        "and demonstration only. The road record is sample data and not an official record.", ss["BodyText"]))
    el.append(Spacer(1, 6))
    el.append(Paragraph(f"Public map: {base}/map | Generated {datetime.now():%d %b %Y %H:%M}", small))
    doc.build(el, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()


def register(app):
    @app.get("/api/reports/analysis/{iid}.pdf")
    def analysis_pdf(iid: int, request: Request):
        base = (os.getenv("RD_PUBLIC_URL") or str(request.base_url)).rstrip("/")
        s = SessionLocal()
        try:
            i = s.get(Inspection, iid)
            if i is None:
                raise HTTPException(404, "inspection not found")
            pdf = build_pdf(s, i, base)
        finally:
            s.close()
        return Response(pdf, media_type="application/pdf",
                        headers={"Content-Disposition": f'inline; filename="analysis_{iid}.pdf"'})

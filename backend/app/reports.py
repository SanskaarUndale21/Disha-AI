"""CSV / PDF reports and YOLO-format export of verified labels."""
import csv
import io
import zipfile
from datetime import datetime
from pathlib import Path

from . import config
from .db import Defect, Detection, Inspection


def defects_csv(s):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["uid", "class", "severity", "severity_score", "risk_score", "risk_level", "status", "trend",
                "report_count", "lat", "lon", "location_source", "road_type", "traffic_level", "first_seen",
                "last_seen", "verified"])
    for d in s.query(Defect).order_by(Defect.risk_score.desc()).all():
        w.writerow([d.uid, d.class_name, d.severity, d.severity_score, d.risk_score, d.risk_level, d.status, d.trend,
                    d.report_count, d.lat, d.lon, d.location_source, d.road_type, d.traffic_level, d.first_seen,
                    d.last_seen, d.verified])
    return buf.getvalue()


def _doc(buf, title):
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate
    return SimpleDocTemplate(buf, pagesize=A4, title=title, leftMargin=36, rightMargin=36, topMargin=36,
                             bottomMargin=36)


def _table(data, widths=None):
    from reportlab.lib import colors
    from reportlab.platypus import Table, TableStyle
    t = Table(data, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d1d5db")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f4f6")]),
    ]))
    return t


def summary_pdf(s, st):
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, Spacer
    buf = io.BytesIO()
    doc = _doc(buf, "Road Damage Report")
    ss = getSampleStyleSheet()
    el = [Paragraph("Road Damage Inspection Report", ss["Title"]),
          Paragraph(f"Generated {datetime.now():%Y-%m-%d %H:%M}", ss["Normal"]), Spacer(1, 10)]
    kpi = [["Inspections", "Detections", "Unique defects", "Active", "Repaired", "High risk", "Duplicates prevented"],
           [st["inspections"], st["detections"], st["unique_defects"], st["active"], st["repaired"], st["high_risk"],
            st["duplicates_prevented"]]]
    el += [_table(kpi), Spacer(1, 12), Paragraph("Defects by class", ss["Heading3"]),
           _table([["Class", "Count"]] + [[k, v] for k, v in st["by_class"].items()]), Spacer(1, 8),
           Paragraph("Defects by risk", ss["Heading3"]),
           _table([["Risk", "Count"]] + [[k, v] for k, v in st["by_risk"].items()]), Spacer(1, 12),
           Paragraph("Defect register (sorted by risk)", ss["Heading3"])]
    rows = [["UID", "Class", "Severity", "Risk", "Status", "Trend", "Reports", "Location", "Last seen"]]
    for d in s.query(Defect).filter(Defect.status != "rejected").order_by(Defect.risk_score.desc()).limit(300):
        loc = f"{d.lat:.5f}, {d.lon:.5f}" if d.lat is not None else "unknown"
        rows.append([d.uid, d.class_name.replace("_", " "), d.severity, f"{d.risk_score:.0f} ({d.risk_level})",
                     d.status, d.trend, d.report_count, loc, f"{d.last_seen:%Y-%m-%d}" if d.last_seen else ""])
    el.append(_table(rows))
    doc.build(el)
    return buf.getvalue()


def inspection_pdf(i: Inspection):
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Image as RLImage, Paragraph, Spacer
    buf = io.BytesIO()
    doc = _doc(buf, f"Inspection {i.id}")
    ss = getSampleStyleSheet()
    loc = f"{i.lat:.6f}, {i.lon:.6f} ({i.location_source})" if i.lat is not None else "unknown"
    el = [Paragraph(f"Inspection #{i.id}: {i.original_name}", ss["Title"]),
          Paragraph(f"Date: {i.captured_at:%Y-%m-%d %H:%M} | Location: {loc} | Road: {i.road_name or '-'} "
                    f"({i.road_type}, traffic {i.traffic_level})", ss["Normal"]), Spacer(1, 8)]
    if i.media_type == "image" and i.annotated_path and Path(i.annotated_path).exists():
        ratio = (i.height or 1) / (i.width or 1)
        el += [RLImage(i.annotated_path, width=17 * cm, height=17 * cm * ratio), Spacer(1, 8)]
    rows = [["Defect", "Class", "Conf", "Severity", "Risk", "Duplicate", "Verification"]]
    for d in i.detections:
        rows.append([d.defect.uid if d.defect else "-", d.final_class.replace("_", " "), f"{d.confidence:.2f}",
                     d.final_severity, f"{d.risk_score:.0f} ({d.risk_level})", "yes" if d.is_duplicate else "no",
                     d.verification])
    el.append(_table(rows))
    doc.build(el)
    return buf.getvalue()


def export_yolo_zip(s):
    cls_idx = {c: k for k, c in enumerate(config.CLASSES)}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("data.yaml", "path: .\ntrain: images\nval: images\nnames:\n" +
                   "".join(f"  {k}: {c}\n" for c, k in cls_idx.items()))
        n = 0
        for i in s.query(Inspection).filter(Inspection.media_type == "image").all():
            good = [d for d in i.detections if d.verification in ("confirmed", "corrected")]
            if not good or not Path(i.stored_path).exists():
                continue
            stem = f"insp_{i.id}"
            z.write(i.stored_path, f"images/{stem}{Path(i.stored_path).suffix}")
            lines = []
            for d in good:
                cx, cy = (d.x1 + d.x2) / 2 / i.width, (d.y1 + d.y2) / 2 / i.height
                bw, bh = (d.x2 - d.x1) / i.width, (d.y2 - d.y1) / i.height
                lines.append(f"{cls_idx.get(d.final_class, 0)} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}")
            z.writestr(f"labels/{stem}.txt", "\n".join(lines) + "\n")
            n += 1
        z.writestr("README.txt", f"{n} verified images exported {datetime.now():%Y-%m-%d %H:%M}. "
                                 "Merge into the training set and run ml/train.py to fine-tune.\n")
    return buf.getvalue()


# ---------------------------------------------------------------- defect complaint / authority reports
def _qr(url, size=110):
    from reportlab.graphics.barcode.qr import QrCodeWidget
    from reportlab.graphics.shapes import Drawing
    w = QrCodeWidget(url)
    x1, y1, x2, y2 = w.getBounds()
    d = Drawing(size, size, transform=[size / (x2 - x1), 0, 0, size / (y2 - y1), 0, 0])
    d.add(w)
    return d


def _img(path, max_w, max_h):
    from reportlab.platypus import Image as RLImage
    try:
        from PIL import Image as PILImage
        with PILImage.open(path) as im:
            w, h = im.size
    except Exception:
        try:
            import cv2
            im = cv2.imread(str(path))
            h, w = im.shape[:2]
        except Exception:
            return None
    k = min(max_w / max(1, w), max_h / max(1, h))
    return RLImage(str(path), width=w * k, height=h * k)


def _fmt_dt(v, fmt="%d %b %Y %H:%M"):
    return v.strftime(fmt) if v else "-"


def _safety_note(level):
    return {"High": "High risk: repair urgently, barricade or mark the spot until repaired.",
            "Medium": "Medium risk: schedule repair in the current maintenance cycle.",
            "Low": "Low risk: monitor and repair with routine maintenance."}.get(level or "", "Risk not assessed.")


def _header(ctx, title, ss):
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, Table, TableStyle
    d = ctx["defect"]
    left = [Paragraph(title, ss["Title"]),
            Paragraph(f"Ticket / defect ID: <b>{d.uid}</b> (#{d.id})", ss["Normal"]),
            Paragraph(f"Generated {datetime.now():%d %b %Y %H:%M}", ss["Normal"]),
            Paragraph(f"Track: {ctx['track_url']}", ss["Normal"])]
    t = Table([[left, _qr(ctx["track_url"])]], colWidths=[14.5 * cm, 4 * cm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return t


def _images_row(ctx):
    from reportlab.lib.units import cm
    from reportlab.platypus import Table
    cells = []
    if ctx.get("annotated"):
        im = _img(ctx["annotated"], 12 * cm, 8 * cm)
        if im:
            cells.append(im)
    if ctx.get("crop"):
        im = _img(ctx["crop"], 6 * cm, 6 * cm)
        if im:
            cells.append(im)
    return Table([cells]) if cells else None


def complaint_pdf(ctx):
    """Citizen-facing complaint report for one defect. ctx is built by ops._report_ctx."""
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, Spacer
    d, det, cost = ctx["defect"], ctx["detection"], ctx["cost"]
    buf = io.BytesIO()
    doc = _doc(buf, f"Complaint {d.uid}")
    ss = getSampleStyleSheet()
    el = [_header(ctx, "Road Damage Complaint", ss), Spacer(1, 8)]
    imgs = _images_row(ctx)
    if imgs:
        el += [imgs, Spacer(1, 8)]
    loc = f"{d.lat:.5f}, {d.lon:.5f}" if d.lat is not None else "unknown"
    size = "-"
    if cost:
        size = f"~{cost['area_m2']:.2f} m2" + (f", ~{cost['length_m']:.1f} m long" if cost.get("length_m") else "")
    rows = [["Field", "Value"],
            ["Date reported", _fmt_dt(d.first_seen)],
            ["Last observed", _fmt_dt(d.last_seen)],
            ["Status", f"{d.status} ({'verified' if d.verified else 'not yet verified'})"],
            ["Location", f"{loc} (source: {d.location_source or 'unknown'})"],
            ["Road type", d.road_type or "unknown"],
            ["Damage type", (d.class_name or "-").replace("_", " ")],
            ["Severity", d.severity or "-"],
            ["Approximate size", size],
            ["Detection confidence", f"{det.confidence:.2f}" if det and det.confidence is not None else "-"],
            ["Risk level", f"{d.risk_level} ({(d.risk_score or 0):.0f}/100)"],
            ["Safety note", Paragraph(_safety_note(d.risk_level), ss["BodyText"])],
            ["Duplicate reports", f"Reported {d.report_count or 1} time(s), merged into this one ticket"]]
    el += [_table(rows, widths=[130, 400]), Spacer(1, 12), Paragraph("Complaint text", ss["Heading3"]),
           Paragraph(ctx["text"], ss["BodyText"]), Spacer(1, 10),
           Paragraph("Scan the QR code or open the tracking link to follow repair progress. Size is an estimate "
                     "from the image and is indicative only.", ss["Italic"])]
    doc.build(el)
    return buf.getvalue()


def authority_pdf(ctx, rates=None):
    """Administrative report: verification log, model details, risk breakdown, cost, history, alerts."""
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, Spacer
    d, det, insp, cost = ctx["defect"], ctx["detection"], ctx["inspection"], ctx["cost"]
    buf = io.BytesIO()
    doc = _doc(buf, f"Authority report {d.uid}")
    ss = getSampleStyleSheet()
    el = [_header(ctx, "Road Defect Authority Report", ss), Spacer(1, 8)]
    loc = f"{d.lat:.6f}, {d.lon:.6f}" if d.lat is not None else "unknown"
    rank = f"{ctx['rank']} of {ctx['active_total']} active defects" if ctx.get("rank") else "not active"
    el += [_table([["Field", "Value"],
                   ["Class", (d.class_name or "-").replace("_", " ")],
                   ["Status / trend", f"{d.status} / {d.trend}"],
                   ["Verified", "yes" if d.verified else "no"],
                   ["Location", f"{loc} ({d.location_source or 'unknown'})"],
                   ["Road / traffic", f"{d.road_type or 'unknown'} / {d.traffic_level or 'unknown'}"],
                   ["First seen / last seen", f"{_fmt_dt(d.first_seen)} / {_fmt_dt(d.last_seen)}"],
                   ["Reports merged", str(d.report_count or 1)],
                   ["Priority rank (by risk)", rank]], widths=[150, 380]), Spacer(1, 8)]
    imgs = _images_row(ctx)
    if imgs:
        el += [imgs, Spacer(1, 8)]

    el.append(Paragraph("AI detection details", ss["Heading3"]))
    el += [_table([["Field", "Value"],
                   ["Detected class", (det.class_name if det else "-") or "-"],
                   ["Confidence", f"{det.confidence:.3f}" if det and det.confidence is not None else "-"],
                   ["Model weights", (insp.model_name if insp and insp.model_name else "not recorded")],
                   ["Inspection", f"#{insp.id} {insp.original_name or ''} ({_fmt_dt(insp.captured_at)})" if insp
                    else "-"]], widths=[150, 380]), Spacer(1, 8)]

    el.append(Paragraph("Verification log", ss["Heading3"]))
    vrows = [["Det", "Inspection", "Class", "Conf", "Severity", "Verification", "By", "At", "Correction"]]
    for x in ctx["detections"]:
        corr = ", ".join(v for v in (x.corrected_class, x.corrected_severity) if v) or "-"
        vrows.append([x.id, x.inspection_id, (x.class_name or "").replace("_", " "),
                      f"{x.confidence:.2f}" if x.confidence is not None else "-", x.severity or "-", x.verification,
                      x.verified_by or "-", _fmt_dt(x.verified_at, "%Y-%m-%d"), corr])
    el += [_table(vrows), Spacer(1, 8)]

    el.append(Paragraph("Severity and risk", ss["Heading3"]))
    br = ctx.get("breakdown") or {}
    el += [Paragraph(f"Severity {d.severity} (score {(d.severity_score or 0):.2f}). Risk "
                     f"{(d.risk_score or 0):.1f}/100 ({d.risk_level}). {_safety_note(d.risk_level)}", ss["BodyText"]),
           _table([["Component", "Points"]] + [[k.replace("_", " "), v] for k, v in br.items()], widths=[200, 100]),
           Spacer(1, 8)]

    el.append(Paragraph("Repair cost estimate (INR, planning assumptions)", ss["Heading3"]))
    if cost:
        crows = [["Item", "Value"],
                 ["Basis", cost.get("basis", "-")],
                 ["Area", f"{cost['area_m2']:.3f} m2"],
                 ["Depth / volume", f"{cost['depth_cm']:.0f} cm / {cost['volume_m3']:.4f} m3"],
                 ["Material", f"{cost['material']}: {cost['material_cost']:,}"],
                 ["Labour", f"{cost['labour_cost']:,}"],
                 ["Traffic management", f"{cost['traffic_cost']:,}"],
                 ["Total (incl. contingency)", f"{cost['total_cost']:,}"]]
        if cost.get("length_m"):
            crows.insert(3, ["Crack length", f"{cost['length_m']:.2f} m"])
        el.append(_table(crows, widths=[200, 330]))
        if rates:
            el.append(Paragraph(f"Contingency {int(rates.get('contingency', 0) * 100)}%. Rates are assumptions "
                                f"(see /api/ops/rates).", ss["Italic"]))
    else:
        el.append(Paragraph("Not a damage class: no repair cost.", ss["BodyText"]))
    el.append(Spacer(1, 8))

    el.append(Paragraph("Progress history", ss["Heading3"]))
    hrows = [["Observed", "Inspection", "Present", "Area ratio", "Severity score", "Risk", "Trend"]]
    for h in ctx["history"]:
        hrows.append([_fmt_dt(h.observed_at), h.inspection_id, "yes" if h.present else "no",
                      f"{h.area_ratio:.4f}" if h.area_ratio is not None else "-",
                      f"{h.severity_score:.2f}" if h.severity_score is not None else "-",
                      f"{h.risk_score:.0f}" if h.risk_score is not None else "-", h.trend or "-"])
    el += [_table(hrows) if len(hrows) > 1 else Paragraph("No history recorded.", ss["BodyText"]), Spacer(1, 8)]

    el.append(Paragraph("Open alerts", ss["Heading3"]))
    if ctx["alerts"]:
        el.append(_table([["Level", "Type", "Status", "Message"]] +
                         [[a["level"], a["type"], a["status"], Paragraph(a["message"], ss["BodyText"])]
                          for a in ctx["alerts"]], widths=[50, 70, 70, 340]))
    else:
        el.append(Paragraph("No open alerts.", ss["BodyText"]))
    el += [Spacer(1, 8), Paragraph("Complaint text", ss["Heading3"]), Paragraph(ctx["text"], ss["BodyText"])]
    doc.build(el)
    return buf.getvalue()

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

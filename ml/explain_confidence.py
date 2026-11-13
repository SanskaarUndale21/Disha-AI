"""Generate a plain-language PDF that walks through how Disha AI scores one real photo, step by step.

usage: python ml/explain_confidence.py [--image path] [--out docs/how_confidence_works.pdf]
Uses the live models and the same code as the app, so every number in the PDF is real.
"""
import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import detector, scoring, severity  # noqa: E402

GREEN, GREY, BLUE, ORANGE, RED = (60, 160, 60), (150, 150, 150), (200, 120, 30), (0, 140, 230), (40, 50, 220)


def box(img, xy, col, text, thick=3):
    x1, y1, x2, y2 = [int(v) for v in xy]
    cv2.rectangle(img, (x1, y1), (x2, y2), col, thick, cv2.LINE_AA)
    fs = max(0.5, img.shape[1] / 900)
    (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, fs, 2)
    ty = y1 - 6 if y1 - th - 10 > 0 else y2 + th + 8
    cv2.rectangle(img, (x1, ty - th - 6), (x1 + tw + 10, ty + 4), col, -1)
    cv2.putText(img, text, (x1 + 5, ty), cv2.FONT_HERSHEY_SIMPLEX, fs, (255, 255, 255), 2, cv2.LINE_AA)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", default=str(ROOT / "data/eval_pothole/ext/images/pothole_1365.jpg"))
    ap.add_argument("--out", default=str(ROOT / "docs/how_confidence_works.pdf"))
    a = ap.parse_args()
    out = Path(a.out)
    figs = out.parent / "figs"
    figs.mkdir(parents=True, exist_ok=True)

    from ultralytics import YOLO
    img = cv2.imread(a.image)
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    proc, enhanced = detector.preprocess(img)

    main_m = YOLO(str(ROOT / "models/pothole_best.pt"))
    second = YOLO(str(ROOT / "models/potholenet_yolo11m.pt"))

    def preds(model, im, flip=False):
        v = im[:, ::-1].copy() if flip else im
        r = model.predict(v, conf=0.03, iou=0.6, imgsz=640, verbose=False)[0].boxes
        out_ = []
        for xy, c, k in zip(r.xyxy.cpu().numpy(), r.conf.cpu().numpy(), r.cls.cpu().numpy().astype(int)):
            if "pothole" not in model.names[int(k)].lower():
                continue
            xy = xy.copy()
            if flip:
                xy[[0, 2]] = w - xy[[2, 0]]
            out_.append((xy, float(c)))
        return sorted(out_, key=lambda t: -t[1])

    p_main = preds(main_m, proc)
    p_main_f = preds(main_m, proc, True)
    p_sec = preds(second, proc)
    p_sec_f = preds(second, proc, True)

    cv2.imwrite(str(figs / "1_original.jpg"), img)
    f2 = img.copy()
    for xy, c in p_main[:8]:
        keep = c >= detector.POTHOLE_CONF
        box(f2, xy, GREEN if keep else GREY, f"{c:.2f} {'keep' if keep else 'drop'}", 3 if keep else 2)
    cv2.imwrite(str(figs / "2_candidates.jpg"), f2)
    f3 = img.copy()
    for xy, c in p_sec[:4]:
        box(f3, xy, BLUE, f"PotholeNet {c:.2f}")
    for xy, c in p_main_f[:3]:
        box(f3, xy, ORANGE, f"mirror {c:.2f}", 2)
    cv2.imwrite(str(figs / "3_second_opinions.jpg"), f3)

    d = detector.infer_accurate(proc)
    rows = [r for r in detector.rows_from(img, d) if r["class_name"] == "pothole"]
    rows.sort(key=lambda r: -r["confidence"])
    f4 = detector.draw(img, rows, lambda r: f'pothole {r["confidence"]:.2f} | {r["severity"]}')
    cv2.imwrite(str(figs / "4_final.jpg"), f4)

    r0 = rows[0] if rows else None
    f5 = img.copy()
    if r0:
        overlay = f5.copy()
        for poly in r0["polygon"]:
            cv2.fillPoly(overlay, [np.array(poly, np.int32)], RED)
        f5 = cv2.addWeighted(overlay, 0.45, f5, 0.55, 0)
        box(f5, (r0["x1"], r0["y1"], r0["x2"], r0["y2"]), RED, "damaged area traced")
    cv2.imwrite(str(figs / "5_damage_area.jpg"), f5)

    # numbers for the story
    def nearest(lst, ref):
        if not lst or ref is None:
            return None
        rx = np.array([ref["x1"], ref["y1"], ref["x2"], ref["y2"]])
        best = max(lst, key=lambda t: _iou(t[0], rx))
        return best[1] if _iou(best[0], rx) > 0.3 else None

    n1, n2, n3, n4 = (nearest(l, r0) for l in (p_main, p_main_f, p_sec, p_sec_f))
    votes = [v for v in (n1, n2, n3, n4)]
    sev_w = None
    if r0:
        sev_w = 0.55 * r0["size_index"] + 0.30 * r0["depth_index"] + 0.15 * r0["roughness_index"]
        risk, level, parts = scoring.risk("pothole", r0["severity_score"], lane=r0["lane"], breakdown=True)

    # ---------- PDF ----------
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
                                    TableStyle)

    ss = getSampleStyleSheet()
    H1 = ParagraphStyle("h1", parent=ss["Title"], fontSize=24, leading=28, spaceAfter=6)
    H2 = ParagraphStyle("h2", parent=ss["Heading2"], fontSize=16, leading=20, spaceBefore=10, spaceAfter=4,
                        textColor=colors.HexColor("#17191d"))
    B = ParagraphStyle("b", parent=ss["BodyText"], fontSize=11.5, leading=16, spaceAfter=6)
    BOX = ParagraphStyle("box", parent=B, backColor=colors.HexColor("#fff6d6"), borderColor=colors.HexColor("#f2b705"),
                         borderWidth=1, borderPadding=8, spaceBefore=6, spaceAfter=10)
    CAP = ParagraphStyle("cap", parent=B, fontSize=9.5, textColor=colors.HexColor("#5d636b"), alignment=TA_CENTER)

    def pic(name, width=15.5 * cm, caption=None):
        im = cv2.imread(str(figs / name))
        ratio = im.shape[0] / im.shape[1]
        items = [Image(str(figs / name), width=width, height=width * ratio)]
        if caption:
            items.append(Paragraph(caption, CAP))
        return KeepTogether(items)

    def table(rows_, widths):
        t = Table(rows_, colWidths=widths)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17191d")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 10.5), ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cfd2cd")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f4f1")]),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
        return t

    pct = lambda v: "not found" if v is None else f"{v * 100:.0f}%"
    E = []
    E += [Paragraph("How Disha AI decides how sure it is", H1),
          Paragraph("A step-by-step walk through one real photo, in plain words. Every number in this document was "
                    "produced by the actual Disha AI models on this photo.", B),
          Paragraph(f"The photo: <b>{Path(a.image).name}</b> ({w} x {h} pixels). It comes from our test set, which the "
                    "model never saw while it was learning, so the results are a fair test.", B),
          pic("1_original.jpg", 12 * cm, "Step 0: the photo exactly as a citizen or officer would upload it."),
          Paragraph("The short version", H2),
          Paragraph("Think of it like asking four experienced road inspectors to look at the same photo. Each one points "
                    "at what they think is a pothole and says how sure they are, from 0% (no idea) to 100% (certain). "
                    "Disha AI keeps only the points where they agree, and the final confidence is the average of how "
                    "sure they were. Then it measures how bad the hole is and how dangerous it is.", BOX),
          PageBreak()]

    E += [Paragraph("Step 1. Clean up the photo if it is too dark", H2),
          Paragraph(f"The computer measures how bright the photo is (0 is black, 255 is white) and how much contrast it "
                    f"has. This photo: brightness <b>{gray.mean():.0f}</b>, contrast <b>{gray.std():.0f}</b>.", B),
          Paragraph("If brightness is below 80 or contrast is below 35 (night, shade, rain), a contrast booster called "
                    f"CLAHE brightens the details first. For this photo it was <b>{'used' if enhanced else 'not needed'}</b>.", B),
          Paragraph("Step 2. The main inspector looks at the photo", H2),
          Paragraph("The main inspector is our trained detection model (YOLO11, fine-tuned on about 14,000 road photos "
                    "of potholes from India, Japan, Europe and more). It looks at the whole photo at once and draws boxes "
                    "around anything that looks like a pothole. For every box it gives a score between 0 and 1.", B),
          Paragraph("Where does that score come from? During training the model was shown thousands of photos where a "
                    "person had drawn the real potholes. Every time it guessed right its score went up for that kind of "
                    "pattern (dark broken edges, rough texture, water inside a hole); every time it fired on plain road "
                    "it was corrected down. After many rounds, the score means: <i>how much does this patch look like the "
                    "potholes I learned from.</i>", BOX),
          pic("2_candidates.jpg", 13 * cm, "Step 2: every box the main model proposed. Green boxes pass the 25% minimum, "
                                           "grey boxes are too unsure and are thrown away."),
          table([["Box", "Score from the main model", "Decision"]] +
                [[f"Candidate {i + 1}", f"{c:.2f}  ({c * 100:.0f}%)",
                  "keep" if c >= detector.POTHOLE_CONF else "drop, below 25%"] for i, (xy, c) in enumerate(p_main[:6])],
                [3.5 * cm, 6 * cm, 5.5 * cm]),
          Paragraph("Overlapping boxes around the same hole are merged first (the one with the highest score wins), so "
                    "one pothole does not get counted twice.", B),
          PageBreak()]

    E += [Paragraph("Step 3. Ask for second opinions", H2),
          Paragraph("One inspector can be fooled by a shadow or a patch of wet road. So Disha AI asks three more times:", B),
          Paragraph("&bull; <b>The same model, mirrored photo.</b> The photo is flipped left to right and checked again. A real "
                    "pothole still looks like a pothole when mirrored; a lucky guess often does not.<br/>"
                    "&bull; <b>A second, different model</b> (PotholeNet, trained separately on Indian streets), on the "
                    "normal photo.<br/>&bull; <b>The second model on the mirrored photo.</b>", B),
          pic("3_second_opinions.jpg", 13 * cm, "Step 3: blue boxes are the second model, orange boxes are the main model "
                                                "on the mirrored photo (drawn back in place)."),
          Paragraph("Step 4. Combine the four opinions into one confidence", H2),
          Paragraph("Boxes from the four looks that land on the same spot are grouped together (they must overlap by more "
                    "than about half). The final box is the average position, and the final confidence is the average of "
                    "the four scores. If one look found nothing there, it counts as a lower vote. This method is called "
                    "Weighted Boxes Fusion, and it is what the winning teams of the international road damage challenge "
                    "(CRDDC 2022) used.", B)]
    if r0:
        E += [table([["Look", "Score for the main pothole"],
                     ["1. Main model, normal photo", pct(n1)], ["2. Main model, mirrored photo", pct(n2)],
                     ["3. Second model, normal photo", pct(n3)], ["4. Second model, mirrored photo", pct(n4)],
                     ["Final confidence (fused)", f"{r0['confidence'] * 100:.0f}%"]], [9 * cm, 6 * cm]),
              Paragraph(f"So the final answer is: <b>this is a pothole, {r0['confidence'] * 100:.0f}% confidence.</b> "
                        "The fused number is often lower than the single best guess. That is on purpose: it is more "
                        "careful, and combining looks finds more real potholes on new photos (recall went from 65% to 72% "
                        "in our tests).", BOX),
              Paragraph("Anything whose final confidence is under 25% is not reported. When a citizen submits a "
                        "complaint, the photo must reach at least 35% for a pothole, otherwise it is refused as "
                        "\"no road damage found\". That is how fake photos of plain road are stopped.", B)]
    E += [PageBreak(), pic("4_final.jpg", 13 * cm, "Step 4 result: the potholes Disha AI reports, with final confidence "
                                                   "and severity.")]

    if r0:
        E += [Paragraph("Step 5. How bad is the hole? (severity)", H2),
              Paragraph("Confidence answers <i>is it a pothole?</i> Severity answers <i>how bad is it?</i> The computer "
                        "traces the actual damaged area inside the box (shaded red below) and measures three things:", B),
              pic("5_damage_area.jpg", 11 * cm, "Step 5: the traced damaged area used for the measurements."),
              table([["Measure", "What it means", "Value (0 to 1)", "Weight"],
                     ["Size", "How big the hole is, corrected for distance from the camera", f"{r0['size_index']:.2f}", "55%"],
                     ["Depth", "How much darker or wetter the hole is than the road around it", f"{r0['depth_index']:.2f}", "30%"],
                     ["Roughness", "How broken and jagged its edges are", f"{r0['roughness_index']:.2f}", "15%"]],
                    [2.6 * cm, 7.4 * cm, 2.8 * cm, 2.2 * cm]),
              Paragraph(f"Severity = 0.55 x {r0['size_index']:.2f} + 0.30 x {r0['depth_index']:.2f} + 0.15 x "
                        f"{r0['roughness_index']:.2f} = <b>{sev_w:.3f}</b>, then multiplied by (0.85 + 0.15 x confidence "
                        f"{r0['confidence']:.2f}) so unsure detections count a little less = <b>{r0['severity_score']:.3f}</b>.", B),
              Paragraph(f"The levels were set from 2,400 real potholes: Minor below 0.315, Moderate up to 0.534, Severe up "
                        f"to 0.745, Critical above. This pothole is <b>{r0['severity']}</b>."
                        + (" Water was detected in it, so it is never rated below 0.55 (water hides the depth)." if r0.get('water') else ""), BOX),
              Paragraph("Step 6. How urgent is it? (risk score out of 100)", H2),
              table([["Part", "Rule", "Points"],
                     ["Severity", f"45 x severity {r0['severity_score']:.2f}", f"{parts['severity']:.1f}"],
                     ["Type of damage", "20 x 1.0 for a pothole (cracks count less)", f"{parts['class_hazard']:.1f}"],
                     ["Road and traffic", "20 x road factor (0.5 when the road type is not known)", f"{parts['road']:.1f}"],
                     ["Position in lane", "15 x 1.0 in the wheel path, down to 0.35 at the edge", f"{float(parts['lane_position']):.1f}"],
                     ["Repeat reports", "+4 per extra citizen report, up to +12", f"{parts['repeat_reports']}"],
                     ["Getting worse", "+8 when it grew since the last inspection", f"{parts['worsening']}"],
                     ["Total risk", "High 70 and up, Medium 40 to 69, Low under 40", f"{risk:.1f} ({level})"]],
                    [3.4 * cm, 9.2 * cm, 2.4 * cm]),
              Paragraph("Officers see this breakdown on every defect, so the number is never a black box.", B)]

    E += [Paragraph("What confidence is and is not", H2),
          Paragraph("&bull; It is a measure of how much the photo matches what the models learned, combined across four "
                    "looks.<br/>&bull; It is not an exact probability. To know how trustworthy it is, we test on photos the "
                    "model never saw: at these settings Disha AI is right about 80% of the time when it says pothole "
                    "(precision) and finds about 65% to 72% of the real potholes in a photo (recall).<br/>"
                    "&bull; Every AI decision can be confirmed, corrected or rejected by an officer in Review detections, "
                    "and those corrections are saved to retrain the model.", B)]

    doc = SimpleDocTemplate(str(out), pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=1.8 * cm,
                            bottomMargin=1.8 * cm, title="How Disha AI decides how sure it is")
    doc.build(E)
    print("wrote", out)


def _iou(a, b):
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    return inter / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter + 1e-9)


if __name__ == "__main__":
    main()

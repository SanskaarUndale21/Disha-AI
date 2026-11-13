"""Calibrate severity normalisers on ground-truth pothole boxes.

Runs the OpenCV analysis on every GT pothole box of data/eval_pothole/{ext,rdd} and prints percentiles of the raw
size / contrast / edge measures. size_ref, depth_ref, rough_ref in severity.CAL are set near the 90th percentile;
Low/Medium/High cut points are set at the 40th / 80th percentile of the resulting score (40% Low, 40% Medium,
20% High), so High is reserved for the worst fifth of real potholes.
"""
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app import severity  # noqa: E402

raw, scores = [], []
for d in ("ext", "rdd"):
    base = ROOT / "data" / "eval_pothole" / d
    for p in sorted((base / "images").iterdir()):
        im = cv2.imread(str(p))
        h, w = im.shape[:2]
        for l in (base / "labels" / (p.stem + ".txt")).read_text().split("\n"):
            if not l.strip():
                continue
            _, cx, cy, bw, bh = map(float, l.split())
            r = severity.analyze(im, "pothole", (cx - bw / 2) * w, (cy - bh / 2) * h, (cx + bw / 2) * w,
                                 (cy + bh / 2) * h, 1.0)
            raw.append([r["raw"]["size"], r["raw"]["contrast"], r["raw"]["edges"]])
            scores.append(r["severity_score"])
raw = np.array(raw)
for i, n in enumerate(["size", "contrast", "edges"]):
    print(n, "p10/50/90:", np.percentile(raw[:, i], [10, 50, 90]).round(4))
s = np.array(scores)
print("n", len(s), "score p40/p80:", np.percentile(s, [40, 80]).round(3))
print("share Low/Med/High with current CAL:", [round(float(x), 3) for x in (
    (s < severity.CAL["low_max"]).mean(), ((s >= severity.CAL["low_max"]) & (s < severity.CAL["med_max"])).mean(),
    (s >= severity.CAL["med_max"]).mean())])

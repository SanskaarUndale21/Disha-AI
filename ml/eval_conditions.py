"""Pothole accuracy per visibility condition (day, night, fog, smoke, dust, rain) for one or more models.

Test sets are held out from training; the condition sets are photometric copies of the external test set
(boxes unchanged), built with ml/add_conditions.py.

usage: python ml/eval_conditions.py --weights models/pothole_best.pt models/pothole_wx.pt --out models/conditions.json
"""
import argparse
import json
from pathlib import Path

from eval_boxes import evaluate

ROOT = Path(__file__).resolve().parents[1]
SETS = [("Day", "ext"), ("Night", "ext_night"), ("Fog", "ext_fog"), ("Smoke", "ext_smoke"), ("Dust", "ext_dust"),
        ("Rain", "ext_rain"), ("Hard RDD day", "rdd"), ("Hard RDD night", "rdd_night")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", nargs="+", required=True)
    ap.add_argument("--out", default=str(ROOT / "models" / "conditions.json"))
    a = ap.parse_args()
    from ultralytics import YOLO
    res = {}
    for w in a.weights:
        m = YOLO(w)
        cmap = {k: 0 for k, v in m.names.items() if "pothole" in v.lower()}
        rows = {}
        for label, d in SETS:
            p = ROOT / "data" / "eval_pothole" / d
            if not p.exists():
                continue
            r = evaluate(w, p, cmap, models=m)
            rows[label] = {k: r[k] for k in ("precision", "recall", "f1", "map50")}
            print(Path(w).name, label, rows[label], flush=True)
        res[Path(w).name] = rows
    Path(a.out).write_text(json.dumps({"sets": [s for s, _ in SETS], "models": res}, indent=2))
    print("wrote", a.out)


if __name__ == "__main__":
    main()

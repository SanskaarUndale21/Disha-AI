"""Evaluate a YOLO model on the held-out split: precision, recall, F1, mAP@50, mAP@50-95, confusion matrix.

Writes models/metrics.json and models/confusion_matrix.png (consumed by the dashboard).

usage: python ml/evaluate.py --weights models/best.pt --data data/merged/data.yaml --split test
"""
import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.config import canonical_class  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", default=str(ROOT / "models" / "best.pt"))
    ap.add_argument("--data", default=str(ROOT / "data" / "merged" / "data.yaml"))
    ap.add_argument("--split", default="test")
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--out", default=str(ROOT / "models"))
    ap.add_argument("--tag", default="")
    a = ap.parse_args()

    from ultralytics import YOLO
    model = YOLO(a.weights)
    r = model.val(data=a.data, split=a.split, imgsz=a.imgsz, batch=a.batch, plots=True, verbose=False,
                  project=str(ROOT / "runs" / "eval"), name=Path(a.weights).stem + (a.tag and "_" + a.tag),
                  exist_ok=True)
    names = {int(k): canonical_class(v) for k, v in model.names.items()}
    box = r.box
    per_class = []
    for i, c in enumerate(box.ap_class_index):
        p, rc = float(box.p[i]), float(box.r[i])
        per_class.append({"class": names[int(c)], "precision": round(p, 4), "recall": round(rc, 4),
                          "f1": round(2 * p * rc / (p + rc + 1e-9), 4), "map50": round(float(box.ap50[i]), 4),
                          "map50_95": round(float(box.ap[i]), 4)})
    mp, mr = float(box.mp), float(box.mr)
    cm = r.confusion_matrix.matrix.astype(int).tolist() if r.confusion_matrix is not None else None
    out = {
        "weights": Path(a.weights).name, "data": Path(a.data).as_posix(), "split": a.split, "imgsz": a.imgsz,
        "evaluated_at": datetime.now().isoformat(timespec="seconds"),
        "overall": {"precision": round(mp, 4), "recall": round(mr, 4), "f1": round(2 * mp * mr / (mp + mr + 1e-9), 4),
                    "map50": round(float(box.map50), 4), "map50_95": round(float(box.map), 4)},
        "per_class": per_class,
        "confusion_matrix": {"labels": [names[i] for i in sorted(names)] + ["background"], "matrix": cm},
        "speed_ms": {k: round(v, 2) for k, v in r.speed.items()},
    }
    outdir = Path(a.out)
    outdir.mkdir(parents=True, exist_ok=True)
    fname = "metrics.json" if not a.tag else f"metrics_{a.tag}.json"
    (outdir / fname).write_text(json.dumps(out, indent=2))
    cmp = Path(r.save_dir) / "confusion_matrix_normalized.png"
    if cmp.exists() and not a.tag:
        shutil.copy(cmp, outdir / "confusion_matrix.png")
    print(json.dumps(out["overall"], indent=2))
    for pc in per_class:
        print(pc)


if __name__ == "__main__":
    main()

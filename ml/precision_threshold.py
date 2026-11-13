"""Find the confidence cut-off at which pothole detections are right at least TARGET (default 85%) of the time.

Runs a model on held-out pothole test sets, matches every prediction to the ground truth (IoU >= 0.5), and sweeps the
confidence threshold. Output: precision and recall at each threshold, plus the lowest threshold that reaches the target.
The app labels detections at or above that threshold "high confidence" and the rest "possible".

usage: python ml/precision_threshold.py --weights models/pothole_best.pt --sets ext rdd ext_night ext_fog --target 0.85
"""
import argparse
import json
from pathlib import Path

import numpy as np
import torch

from eval_boxes import load_labels

ROOT = Path(__file__).resolve().parents[1]


def collect(model, cmap, data_dir):
    from ultralytics.utils.metrics import box_iou
    confs, tps, n_gt = [], [], 0
    imgs = sorted((Path(data_dir) / "images").iterdir())
    for i in range(0, len(imgs), 16):
        batch = imgs[i:i + 16]
        res = model.predict([str(p) for p in batch], imgsz=640, conf=0.05, iou=0.6, verbose=False, quantize=16)
        for p, r in zip(batch, res):
            h, w = r.orig_shape
            gt = load_labels(Path(data_dir) / "labels" / (p.stem + ".txt"), w, h)
            n_gt += len(gt)
            b = r.boxes
            keep = [k for k, c in enumerate(b.cls.cpu().numpy().astype(int)) if c in cmap]
            pb, ps = b.xyxy.cpu()[keep], b.conf.cpu().numpy()[keep]
            order = np.argsort(-ps)
            used = set()
            iou = box_iou(torch.tensor(gt[:, 1:], dtype=torch.float), pb).numpy() if len(gt) and len(pb) else None
            for j in order:
                hit = False
                if iou is not None:
                    cand = [(iou[g, j], g) for g in range(len(gt)) if g not in used and iou[g, j] >= 0.5]
                    if cand:
                        _, g = max(cand)
                        used.add(g)
                        hit = True
                confs.append(float(ps[j]))
                tps.append(hit)
    return np.array(confs), np.array(tps), n_gt


def curve(confs, tps, n_gt):
    rows = []
    for t in np.arange(0.25, 0.96, 0.05):
        sel = confs >= t
        n = int(sel.sum())
        tp = int(tps[sel].sum())
        rows.append({"threshold": round(float(t), 2), "detections": n,
                     "precision": round(tp / n, 4) if n else None, "recall": round(tp / max(1, n_gt), 4)})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", default=str(ROOT / "models" / "pothole_best.pt"))
    ap.add_argument("--sets", nargs="+", default=["ext", "rdd"])
    ap.add_argument("--target", type=float, default=0.85)
    ap.add_argument("--out", default=str(ROOT / "models" / "confidence_levels.json"))
    a = ap.parse_args()
    from ultralytics import YOLO
    m = YOLO(a.weights)
    cmap = {k for k, v in m.names.items() if "pothole" in v.lower()}
    allc, allt, alln = [], [], 0
    per_set = {}
    for s in a.sets:
        c, t, n = collect(m, cmap, ROOT / "data" / "eval_pothole" / s)
        allc.append(c); allt.append(t); alln += n
        per_set[s] = curve(c, t, n)
        print(s, "done", flush=True)
    c, t = np.concatenate(allc), np.concatenate(allt)
    overall = curve(c, t, alln)
    reach = next((r for r in overall if r["precision"] is not None and r["precision"] >= a.target), None)
    out = {"weights": Path(a.weights).name, "target_precision": a.target, "sets": a.sets,
           "high_confidence_threshold": reach["threshold"] if reach else None, "at_threshold": reach,
           "overall": overall, "per_set": per_set}
    Path(a.out).write_text(json.dumps(out, indent=2))
    for r in overall:
        print(r)
    print("HIGH CONFIDENCE THRESHOLD:", out["high_confidence_threshold"], reach)


if __name__ == "__main__":
    main()

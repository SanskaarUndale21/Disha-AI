"""Box-level evaluation for any YOLO model (detect or segment) on a YOLO-format folder.

Computes precision, recall, F1 (at the best-F1 confidence) and mAP@50 / mAP@50-95 with Ultralytics' ap_per_class.
usage: python ml/eval_boxes.py --weights W --data data/eval_pothole/ext --cls-map 0:0
       (--cls-map model_class:dataset_class, e.g. 3:0 to score the RDD D40 head against single-class labels)
"""
import argparse
import json
from pathlib import Path

import numpy as np
import torch


def load_labels(p, w, h):
    if not p.exists():
        return np.zeros((0, 5))
    rows = [list(map(float, l.split())) for l in p.read_text().split("\n") if l.strip()]
    if not rows:
        return np.zeros((0, 5))
    a = np.array(rows)[:, :5]
    c, cx, cy, bw, bh = a.T
    return np.stack([c, (cx - bw / 2) * w, (cy - bh / 2) * h, (cx + bw / 2) * w, (cy + bh / 2) * h], 1)


def evaluate(weights, data, cls_map, imgsz=640, conf=0.001, models=None):
    from ultralytics import YOLO
    from ultralytics.utils.metrics import ap_per_class, box_iou
    model = models or YOLO(weights)
    iouv = torch.linspace(0.5, 0.95, 10)
    stats = []
    imgs = sorted((Path(data) / "images").iterdir())
    for i in range(0, len(imgs), 16):
        batch = imgs[i:i + 16]
        res = model.predict([str(p) for p in batch], imgsz=imgsz, conf=conf, iou=0.6, verbose=False, half=True)
        for p, r in zip(batch, res):
            h, w = r.orig_shape
            gt = load_labels(Path(data) / "labels" / (p.stem + ".txt"), w, h)
            b = r.boxes
            keep = [k for k, c in enumerate(b.cls.cpu().numpy().astype(int)) if c in cls_map]
            pb = b.xyxy.cpu()[keep]
            pc = torch.tensor([cls_map[int(c)] for c in b.cls.cpu().numpy().astype(int)[keep]], dtype=torch.float)
            ps = b.conf.cpu()[keep]
            correct = torch.zeros(len(pb), 10, dtype=torch.bool)
            if len(gt) and len(pb):
                iou = box_iou(torch.tensor(gt[:, 1:], dtype=torch.float), pb)
                same = torch.tensor(gt[:, :1], dtype=torch.float) == pc[None]
                for j, t in enumerate(iouv):
                    x = torch.where((iou >= t) & same)
                    if x[0].shape[0]:
                        m = torch.cat((torch.stack(x, 1), iou[x[0], x[1]][:, None]), 1).numpy()
                        m = m[m[:, 2].argsort()[::-1]]
                        m = m[np.unique(m[:, 1], return_index=True)[1]]
                        m = m[np.unique(m[:, 0], return_index=True)[1]]
                        correct[m[:, 1].astype(int), j] = True
            stats.append((correct, ps, pc, torch.tensor(gt[:, 0]) if len(gt) else torch.zeros(0)))
    tp, conf_, pcls, tcls = [torch.cat(x, 0).numpy() for x in zip(*stats)]
    out = ap_per_class(tp, conf_, pcls, tcls, plot=False)
    tp_, fp_, p, r, f1, ap = out[:6]
    return {"precision": round(float(p.mean()), 4), "recall": round(float(r.mean()), 4),
            "f1": round(float(f1.mean()), 4), "map50": round(float(ap[:, 0].mean()), 4),
            "map50_95": round(float(ap.mean()), 4), "images": len(imgs)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", required=True)
    ap.add_argument("--data", required=True)
    ap.add_argument("--cls-map", default="0:0")
    ap.add_argument("--imgsz", type=int, default=640)
    a = ap.parse_args()
    cm = {int(k): int(v) for k, v in (x.split(":") for x in a.cls_map.split(","))}
    print(json.dumps(evaluate(a.weights, a.data, cm, a.imgsz)))

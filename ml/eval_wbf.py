"""Evaluate a Weighted Boxes Fusion ensemble of several pothole models (+ optional horizontal-flip TTA).

usage: python ml/eval_wbf.py --data data/eval_pothole/ext --weights models/pothole_best.pt models/potholenet_yolo11m.pt
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch
from ensemble_boxes import weighted_boxes_fusion

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_boxes import load_labels  # noqa: E402


def fused_predict(models, img_path, flip, iou=0.55, skip=0.05, weights=None):
    import cv2
    im = cv2.imread(str(img_path))
    h, w = im.shape[:2]
    B, S, L = [], [], []
    for m, cmap in models:
        views = [(im, False)] + ([(im[:, ::-1].copy(), True)] if flip else [])
        for v, flipped in views:
            r = m.predict(v, imgsz=640, conf=0.01, iou=0.6, verbose=False, quantize=16)[0].boxes
            xy = r.xyxy.cpu().numpy().copy()
            keep = [i for i, c in enumerate(r.cls.cpu().numpy().astype(int)) if c in cmap]
            xy = xy[keep]
            if flipped and len(xy):
                xy[:, [0, 2]] = w - xy[:, [2, 0]]
            xy[:, [0, 2]] /= w
            xy[:, [1, 3]] /= h
            B.append(np.clip(xy, 0, 1).tolist())
            S.append(r.conf.cpu().numpy()[keep].tolist())
            L.append([0] * len(keep))
    wts = weights or [1] * len(B)
    b, s, l = weighted_boxes_fusion(B, S, L, weights=wts, iou_thr=iou, skip_box_thr=skip, conf_type="avg")
    b = np.array(b) * [w, h, w, h] if len(b) else np.zeros((0, 4))
    return b, np.array(s), (h, w)


def main():
    from ultralytics import YOLO
    from ultralytics.utils.metrics import ap_per_class, box_iou
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--weights", nargs="+", required=True)
    ap.add_argument("--flip", action="store_true")
    a = ap.parse_args()
    models = []
    for wpath in a.weights:
        m = YOLO(wpath)
        cmap = {k for k, v in m.names.items() if "pothole" in v.lower()}
        models.append((m, cmap))
    iouv = torch.linspace(0.5, 0.95, 10)
    stats = []
    imgs = sorted((Path(a.data) / "images").iterdir())
    for p in imgs:
        pb, ps, (h, w) = fused_predict(models, p, a.flip)
        gt = load_labels(Path(a.data) / "labels" / (p.stem + ".txt"), w, h)
        pb = torch.tensor(pb, dtype=torch.float)
        correct = torch.zeros(len(pb), 10, dtype=torch.bool)
        if len(gt) and len(pb):
            iou = box_iou(torch.tensor(gt[:, 1:], dtype=torch.float), pb)
            for j, t in enumerate(iouv):
                x = torch.where(iou >= t)
                if x[0].shape[0]:
                    mm = torch.cat((torch.stack(x, 1), iou[x[0], x[1]][:, None]), 1).numpy()
                    mm = mm[mm[:, 2].argsort()[::-1]]
                    mm = mm[np.unique(mm[:, 1], return_index=True)[1]]
                    mm = mm[np.unique(mm[:, 0], return_index=True)[1]]
                    correct[mm[:, 1].astype(int), j] = True
        stats.append((correct, torch.tensor(ps, dtype=torch.float), torch.zeros(len(pb)),
                      torch.zeros(len(gt)) if len(gt) else torch.zeros(0)))
    tp, conf, pcls, tcls = [torch.cat(x, 0).numpy() for x in zip(*stats)]
    _, _, p, r, f1, apv = ap_per_class(tp, conf, pcls, tcls, plot=False)[:6]
    print(json.dumps({"precision": round(float(p.mean()), 4), "recall": round(float(r.mean()), 4),
                      "f1": round(float(f1.mean()), 4), "map50": round(float(apv[:, 0].mean()), 4)}))


if __name__ == "__main__":
    main()

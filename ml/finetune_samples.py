"""Fine-tune the pothole model on the user's own sample footage (samples/images and samples/VIDEOS).

Modular pipeline: extract_frames -> pseudo_label -> build_dataset -> train. Labels are produced by the current
ensemble, keeping only confident, repeatedly seen boxes, then mixed with a slice of the original training set so the
model does not forget general roads. NOTE: results measured on these same samples afterwards are NOT a held-out
accuracy; the held-out photo sets (ml/eval_conditions.py) remain the honest benchmark.

usage: python ml/finetune_samples.py [--every 10] [--epochs 4] [--mix 1500]
"""
import argparse
import glob
import os
import random
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
OUT = ROOT / "data" / "samples_ft"
IMG_EXT = (".jpg", ".jpeg", ".png")
VID_EXT = (".mp4", ".mov", ".avi", ".mkv")


def extract_frames(every: int):
    """Save every Nth frame of each sample video, plus each sample photo, to OUT/raw. Returns [Path]."""
    raw = OUT / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    paths = []
    for f in sorted(glob.glob(str(ROOT / "samples" / "**" / "*"), recursive=True)):
        low = f.lower()
        stem = Path(f).stem.replace(" ", "_")[:40]
        if low.endswith(IMG_EXT):
            img = cv2.imread(f)
            if img is not None:
                p = raw / f"img_{stem}.jpg"
                cv2.imwrite(str(p), img, [cv2.IMWRITE_JPEG_QUALITY, 92])
                paths.append(p)
        elif low.endswith(VID_EXT) and "fall_test" not in low and "synthetic" not in low and "old_codec" not in low:
            cap = cv2.VideoCapture(f)
            i = 0
            while True:
                ok, fr = cap.read()
                if not ok:
                    break
                if i % every == 0:
                    p = raw / f"vid_{stem}_{i:05d}.jpg"
                    cv2.imwrite(str(p), fr, [cv2.IMWRITE_JPEG_QUALITY, 90])
                    paths.append(p)
                i += 1
            cap.release()
    return paths


def pseudo_label(paths, conf_keep=0.40, tile_keep=0.50):
    """Label each frame with the ensemble (full frame + magnified tiles). Returns {path: [(x1,y1,x2,y2),...]}."""
    from app import detector
    from app.detector import CLS_ID
    detector._load()
    labels = {}
    B = 6
    for s in range(0, len(paths), B):
        chunk = paths[s:s + B]
        imgs = [cv2.imread(str(p)) for p in chunk]
        full = detector.infer_batch(imgs, cracks=False, imgsz=640)
        tiles = detector.infer_tiles(imgs, mode="photo")
        for p, im, d, t in zip(chunk, imgs, full, tiles):
            boxes = []
            if len(d):
                m = (d.cls == CLS_ID["pothole"]) & (d.conf >= conf_keep)
                boxes += [tuple(b) for b in d.xyxy[m]]
            if len(t):
                m = t.conf >= tile_keep
                for b in t.xyxy[m]:
                    if not any(_iou(b, x) > 0.4 for x in boxes):
                        boxes.append(tuple(b))
            labels[p] = [b for b in boxes if (b[2] - b[0]) > 6 and (b[3] - b[1]) > 6]
        print(f"labelled {min(s + B, len(paths))}/{len(paths)}", flush=True)
    return labels


def _iou(a, b):
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    u = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / u if u > 0 else 0.0


def build_dataset(labels, mix: int, neg_ratio=0.15, seed=3):
    """Write YOLO labels next to the frames, mix in original images, return the data.yaml path."""
    rnd = random.Random(seed)
    pos = [p for p, b in labels.items() if b]
    neg = [p for p, b in labels.items() if not b]
    neg = rnd.sample(neg, min(len(neg), int(len(pos) * neg_ratio)))
    lab_dir = OUT / "labels"
    lab_dir.mkdir(exist_ok=True)
    keep = pos + neg
    for p in keep:
        h, w = cv2.imread(str(p)).shape[:2]
        lines = [f"0 {(x1 + x2) / 2 / w:.6f} {(y1 + y2) / 2 / h:.6f} {(x2 - x1) / w:.6f} {(y2 - y1) / h:.6f}" for x1, y1, x2, y2 in labels[p]]
        (lab_dir / (p.stem + ".txt")).write_text("\n".join(lines), encoding="utf-8")
    # YOLO finds labels by swapping /images/ for /labels/, so mirror the frames into an images folder
    img_dir = OUT / "images"
    img_dir.mkdir(exist_ok=True)
    listed = []
    for p in keep:
        q = img_dir / p.name
        if not q.exists():
            q.write_bytes(p.read_bytes())
        listed.append(str(q).replace("\\", "/"))
    orig = [l.strip() for l in open(ROOT / "data/pothole_v5/train.txt") if l.strip()]
    listed += rnd.sample(orig, min(mix, len(orig)))
    rnd.shuffle(listed)
    (OUT / "train.txt").write_text("\n".join(listed), encoding="utf-8")
    yaml = OUT / "data.yaml"
    yaml.write_text(f"path: {OUT.as_posix()}\ntrain: train.txt\nval: {(ROOT / 'data/pothole_v5/val.txt').as_posix()}\nnc: 1\nnames: ['pothole']\n", encoding="utf-8")
    print(f"dataset: {len(pos)} frames with potholes, {len(neg)} negatives, {min(mix, len(orig))} original images")
    return yaml


def train(yaml, epochs, name="pothole_v7"):
    from ultralytics import YOLO
    m = YOLO(str(ROOT / "models" / "pothole_best.pt"))
    m.train(data=str(yaml), epochs=epochs, imgsz=640, batch=8, workers=3, device=0, project=str(ROOT / "runs" / "train"), name=name,
            exist_ok=True, optimizer="AdamW", lr0=0.0003, lrf=0.1, cos_lr=True, warmup_epochs=0.3, patience=3, close_mosaic=1,
            amp=True, cache=False, plots=False, hsv_v=0.6, scale=0.5, mosaic=1.0, mixup=0.05, save_period=1)
    return ROOT / "runs" / "train" / name / "weights" / "best.pt"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--every", type=int, default=10)
    ap.add_argument("--epochs", type=int, default=4)
    ap.add_argument("--mix", type=int, default=1500)
    a = ap.parse_args()
    paths = extract_frames(a.every)
    print(f"{len(paths)} frames extracted", flush=True)
    labels = pseudo_label(paths)
    yaml = build_dataset(labels, a.mix)
    from app import detector  # free the GPU memory used for labelling before training starts
    import gc
    import torch
    detector._models = None
    gc.collect()
    torch.cuda.empty_cache()
    best = train(yaml, a.epochs)
    print("BEST", best)


if __name__ == "__main__":
    main()

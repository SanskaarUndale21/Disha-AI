"""Short, efficient fine-tune of the pothole model.

Why the earlier run was slow: it walked 18,799 images per round at 800 px with batch 6 on a 6 GB laptop GPU
(about 50 minutes per round, plus heat pauses). This run uses a curated, source-balanced subset (~6,000 images,
90 percent with potholes and 10 percent road-only negatives), 640 px, a larger batch, a small validation set and
only a few rounds, starting from the current best weights.

usage: python ml/train_fast.py [--epochs 8] [--n 6000] [--name pothole_v5]
"""
import argparse
import collections
import os
import random
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def label_path(img):
    return img.replace("/images/", "/labels/").rsplit(".", 1)[0] + ".txt"


def build_lists(n, seed=7):
    rnd = random.Random(seed)
    src = [l.strip() for l in open(ROOT / "data/pothole_fast/train.txt") if l.strip()]
    pos, neg = collections.defaultdict(list), []
    for p in src:
        try:
            has = os.path.getsize(label_path(p)) > 0
        except OSError:
            has = False
        if has:
            m = re.match(r"([a-zA-Z]+\d*)_", os.path.basename(p))
            pos[m.group(1) if m else "other"].append(p)
        else:
            neg.append(p)
    n_neg = int(n * 0.10)
    n_pos = n - n_neg
    # equal share per source first, then fill the remainder from the biggest sources (keeps variety across datasets)
    chosen, srcs = [], sorted(pos, key=lambda k: len(pos[k]))
    left = n_pos
    for i, k in enumerate(srcs):
        share = left // (len(srcs) - i)
        take = min(len(pos[k]), share)
        chosen += rnd.sample(pos[k], take)
        left -= take
    chosen += rnd.sample(neg, min(len(neg), n_neg))
    rnd.shuffle(chosen)
    val = sorted(os.listdir(ROOT / "data/pothole/val/images"))
    val = [str(ROOT / "data/pothole/val/images" / v).replace("\\", "/") for v in rnd.sample(val, 300)]
    out = ROOT / "data/pothole_v5"
    out.mkdir(exist_ok=True)
    (out / "train.txt").write_text("\n".join(chosen), encoding="utf-8")
    (out / "val.txt").write_text("\n".join(val), encoding="utf-8")
    (out / "data.yaml").write_text(
        f"path: {out.as_posix()}\ntrain: train.txt\nval: val.txt\nnc: 1\nnames: ['pothole']\n", encoding="utf-8")
    print(f"train {len(chosen)} images from {len(srcs)} sources ({len(chosen) - min(len(neg), n_neg)} with potholes), val {len(val)}")
    return out / "data.yaml"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=8)
    ap.add_argument("--n", type=int, default=6000)
    ap.add_argument("--batch", type=int, default=10)
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--base", default=str(ROOT / "models" / "pothole_wx_e2.pt"))
    ap.add_argument("--name", default="pothole_v5")
    a = ap.parse_args()
    data = build_lists(a.n)
    from ultralytics import YOLO
    m = YOLO(a.base)
    m.train(data=str(data), epochs=a.epochs, imgsz=a.imgsz, batch=a.batch, workers=3, device=0, project=str(ROOT / "runs" / "train"),
            name=a.name, exist_ok=True, optimizer="AdamW", lr0=0.0004, lrf=0.1, cos_lr=True, warmup_epochs=0.5, patience=4,
            close_mosaic=2, amp=True, cache=False, plots=False, fliplr=0.5, flipud=0.0,
            hsv_h=0.015, hsv_s=0.7, hsv_v=0.65, scale=0.6, mosaic=1.0, mixup=0.1, degrees=3.0, save_period=1)


if __name__ == "__main__":
    main()

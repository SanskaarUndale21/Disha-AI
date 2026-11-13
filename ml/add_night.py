"""Synthetic night / low-light copies of a YOLO dataset split, for day-and-night robustness.

Each night image keeps the original boxes (geometry is unchanged) and applies a random mix of:
  - exposure drop with gamma 1.8-3.0 (dark scene, shadows crushed more than highlights)
  - colour cast: sodium street-lamp orange or cool moonlight blue, reduced saturation
  - sensor noise (Gaussian + slight chroma noise) as cameras raise ISO at night
  - headlight / street-lamp glare blobs near the bottom or top of the frame
  - mild motion blur (slower shutter) in about half the images

usage:
  python ml/add_night.py --src data/pothole_v3/train --frac 0.3           # adds nt_* copies into the split
  python ml/add_night.py --src data/eval_pothole/ext --dst data/eval_pothole/ext_night --frac 1.0
"""
import argparse
import random
import shutil
from pathlib import Path

import cv2
import numpy as np


def night(img, rng):
    f = img.astype(np.float32) / 255.0
    f = np.power(f, rng.uniform(1.8, 3.0)) * rng.uniform(0.55, 0.85)
    hsv = cv2.cvtColor((f * 255).clip(0, 255).astype(np.uint8), cv2.COLOR_BGR2HSV).astype(np.float32)
    hsv[:, :, 1] *= rng.uniform(0.45, 0.8)
    f = cv2.cvtColor(hsv.clip(0, 255).astype(np.uint8), cv2.COLOR_HSV2BGR).astype(np.float32) / 255.0
    if rng.random() < 0.6:  # sodium lamp
        f *= np.array([0.75, 0.92, 1.12], np.float32)
    else:  # moonlight
        f *= np.array([1.12, 0.98, 0.82], np.float32)
    h, w = f.shape[:2]
    for _ in range(rng.randint(0, 2)):  # glare
        cx, cy = rng.uniform(0.1, 0.9) * w, rng.choice([rng.uniform(0.75, 1.0), rng.uniform(0.0, 0.2)]) * h
        r = rng.uniform(0.08, 0.22) * max(w, h)
        yy, xx = np.mgrid[0:h, 0:w]
        g = np.exp(-(((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * r * r))).astype(np.float32)
        f += g[..., None] * rng.uniform(0.25, 0.6) * np.array([0.8, 0.9, 1.0], np.float32)
    f += np.random.default_rng(rng.randint(0, 10 ** 6)).normal(0, rng.uniform(0.015, 0.04), f.shape).astype(np.float32)
    out = (f.clip(0, 1) * 255).astype(np.uint8)
    if rng.random() < 0.5:
        k = rng.choice([3, 5, 7])
        kernel = np.zeros((k, k), np.float32)
        kernel[k // 2, :] = 1.0 / k
        out = cv2.filter2D(out, -1, kernel)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--dst", default=None, help="separate output dataset (default: add nt_* copies into src)")
    ap.add_argument("--frac", type=float, default=0.3)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    rng = random.Random(a.seed)
    src = Path(a.src)
    dst = Path(a.dst) if a.dst else src
    (dst / "images").mkdir(parents=True, exist_ok=True)
    (dst / "labels").mkdir(parents=True, exist_ok=True)
    imgs = [p for p in sorted((src / "images").iterdir()) if p.suffix.lower() in {".jpg", ".jpeg", ".png"}
            and not p.name.startswith("nt_")]
    rng.shuffle(imgs)
    pick = imgs[: int(len(imgs) * a.frac)]
    n = 0
    for p in pick:
        im = cv2.imread(str(p))
        if im is None:
            continue
        name = ("nt_" if dst == src else "") + p.stem + ".jpg"
        cv2.imwrite(str(dst / "images" / name), night(im, rng), [cv2.IMWRITE_JPEG_QUALITY, 88])
        lab = src / "labels" / (p.stem + ".txt")
        out_lab = dst / "labels" / (Path(name).stem + ".txt")
        if lab.exists():
            shutil.copy(lab, out_lab)
        else:
            out_lab.write_text("")
        n += 1
    if dst != src:
        (dst / "data.yaml").write_text(f"path: {dst.resolve().as_posix()}\ntrain: images\nval: images\ntest: images\n"
                                       f"nc: 1\nnames: ['pothole']\n")
    print(f"wrote {n} night images to {dst}")


if __name__ == "__main__":
    main()

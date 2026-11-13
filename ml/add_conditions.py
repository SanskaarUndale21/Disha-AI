"""Adverse-condition copies of a YOLO dataset split: night, fog, smoke, dust, rain, motion blur.

Boxes are unchanged (photometric effects only), so every copy keeps the original labels.

  night : gamma-darkened, sodium / moonlight cast, sensor noise, lamp glare (see add_night.night)
  fog   : atmospheric scattering model I = J*t + A*(1-t), transmission falls with distance (top of frame)
  smoke : patchy grey-brown haze from multi-octave noise, uneven density
  dust  : warm yellow-brown low-contrast haze plus fine specks
  rain  : streak layer (oriented motion-blurred drops), darkening, slight blur, wet-road sheen
  blur  : camera shake / vehicle vibration

usage:
  python ml/add_conditions.py --src data/pothole_v3/train --frac 0.45            # mixed conditions, into src
  python ml/add_conditions.py --src data/eval_pothole/ext --dst data/eval_pothole/ext_fog --mode fog --frac 1
"""
import argparse
import random
import shutil
from pathlib import Path

import cv2
import numpy as np

from add_night import night

MODES = ["night", "fog", "smoke", "dust", "rain", "blur"]


def _noise_field(h, w, rng, octaves=4):
    f = np.zeros((h, w), np.float32)
    for o in range(octaves):
        s = 2 ** (o + 2)
        g = np.random.default_rng(rng.randint(0, 10 ** 6)).random((s, s)).astype(np.float32)
        f += cv2.resize(g, (w, h), interpolation=cv2.INTER_CUBIC) / (2 ** o)
    f -= f.min()
    return f / (f.max() + 1e-6)


def fog(img, rng):
    h, w = img.shape[:2]
    J = img.astype(np.float32) / 255.0
    depth = np.linspace(1.0, 0.15, h, dtype=np.float32)[:, None] * np.ones((1, w), np.float32)
    beta = rng.uniform(1.2, 2.8)
    t = np.exp(-beta * depth * rng.uniform(0.6, 1.0))[..., None]
    A = rng.uniform(0.75, 0.95)
    out = J * t + A * (1 - t)
    return (out.clip(0, 1) * 255).astype(np.uint8)


def smoke(img, rng):
    h, w = img.shape[:2]
    J = img.astype(np.float32) / 255.0
    dens = (_noise_field(h, w, rng) * rng.uniform(0.45, 0.8))[..., None]
    colour = np.array([0.55, 0.58, 0.6], np.float32) * rng.uniform(0.8, 1.1)
    return ((J * (1 - dens) + colour * dens).clip(0, 1) * 255).astype(np.uint8)


def dust(img, rng):
    h, w = img.shape[:2]
    J = img.astype(np.float32) / 255.0
    a = rng.uniform(0.3, 0.55)
    colour = np.array([0.45, 0.62, 0.78], np.float32)  # BGR warm tan
    haze = (0.6 + 0.4 * _noise_field(h, w, rng, 3))[..., None] * a
    out = J * (1 - haze) + colour * haze
    specks = np.random.default_rng(rng.randint(0, 10 ** 6)).random((h, w)) > 0.997
    out[specks] = colour * 1.2
    return (out.clip(0, 1) * 255).astype(np.uint8)


def rain(img, rng):
    h, w = img.shape[:2]
    out = img.astype(np.float32) * rng.uniform(0.6, 0.85)
    drops = (np.random.default_rng(rng.randint(0, 10 ** 6)).random((h, w)) > rng.uniform(0.992, 0.997)).astype(np.float32)
    k = rng.randint(9, 21)
    kernel = np.zeros((k, k), np.float32)
    kernel[:, k // 2] = 1.0
    M = cv2.getRotationMatrix2D((k / 2, k / 2), rng.uniform(-20, 20), 1.0)
    kernel = cv2.warpAffine(kernel, M, (k, k))
    streaks = cv2.filter2D(drops, -1, kernel / max(1e-6, kernel.sum()) * k * 0.9)
    out += (streaks[..., None] * rng.uniform(45, 95))
    out = cv2.GaussianBlur(out, (3, 3), 0)
    return out.clip(0, 255).astype(np.uint8)


def blur(img, rng):
    k = rng.choice([5, 7, 9, 11])
    kernel = np.zeros((k, k), np.float32)
    kernel[k // 2, :] = 1.0 / k
    M = cv2.getRotationMatrix2D((k / 2, k / 2), rng.uniform(0, 180), 1.0)
    kernel = cv2.warpAffine(kernel, M, (k, k))
    return cv2.filter2D(img, -1, kernel / max(1e-6, kernel.sum()))


FX = {"night": night, "fog": fog, "smoke": smoke, "dust": dust, "rain": rain, "blur": blur}
WEIGHTS = {"night": 0.3, "fog": 0.17, "smoke": 0.12, "dust": 0.13, "rain": 0.16, "blur": 0.12}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--dst", default=None)
    ap.add_argument("--mode", default="mix", choices=MODES + ["mix"])
    ap.add_argument("--frac", type=float, default=0.45)
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--nc", default="1")
    ap.add_argument("--names", default="['pothole']")
    a = ap.parse_args()
    rng = random.Random(a.seed)
    src, dst = Path(a.src), Path(a.dst) if a.dst else Path(a.src)
    (dst / "images").mkdir(parents=True, exist_ok=True)
    (dst / "labels").mkdir(parents=True, exist_ok=True)
    imgs = [p for p in sorted((src / "images").iterdir()) if p.suffix.lower() in {".jpg", ".jpeg", ".png"}
            and not p.name.startswith(("nt_", "wx_"))]
    rng.shuffle(imgs)
    counts = {}
    for p in imgs[: int(len(imgs) * a.frac)]:
        im = cv2.imread(str(p))
        if im is None:
            continue
        mode = a.mode if a.mode != "mix" else rng.choices(list(WEIGHTS), list(WEIGHTS.values()))[0]
        out = FX[mode](im, rng)
        name = (f"wx_{mode}_" if dst == src else "") + p.stem + ".jpg"
        cv2.imwrite(str(dst / "images" / name), out, [cv2.IMWRITE_JPEG_QUALITY, 88])
        lab = src / "labels" / (p.stem + ".txt")
        tgt = dst / "labels" / (Path(name).stem + ".txt")
        shutil.copy(lab, tgt) if lab.exists() else tgt.write_text("")
        counts[mode] = counts.get(mode, 0) + 1
    if dst != src:
        (dst / "data.yaml").write_text(f"path: {dst.resolve().as_posix()}\ntrain: images\nval: images\ntest: images\n"
                                       f"nc: {a.nc}\nnames: {a.names}\n")
    print("wrote", counts, "->", dst)


if __name__ == "__main__":
    main()

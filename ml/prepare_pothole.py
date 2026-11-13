"""Single-class pothole dataset for the pothole specialist model (class 0 = pothole).

train: RDD2022 train images with D40 + 2000 pothole-free RDD road images (negatives)
       + potholes-yolov8 train + muskan train + lorenzo (85%, manholes/cracks left unlabeled = hard negatives)
val  : RDD2022 holdout-val D40 images + muskan valid + lorenzo (15%)
test : data/eval_pothole/{ext,rdd}  (never trained on)

Near-duplicate images (dHash Hamming <= 4) of any test image are dropped from train/val to avoid leakage.
"""
import random
import shutil
import sys
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "pothole"
IMG = {".jpg", ".jpeg", ".png"}


def dhash(p):
    g = cv2.imread(str(p), cv2.IMREAD_GRAYSCALE)
    if g is None:
        return None
    g = cv2.resize(g, (9, 8), interpolation=cv2.INTER_AREA)
    return int("".join("1" if b else "0" for b in (g[:, 1:] > g[:, :-1]).flatten()), 2)


def read_labels(p, keep):
    if not p.exists():
        return []
    out = []
    for l in p.read_text().split("\n"):
        s = l.split()
        if len(s) == 5 and int(float(s[0])) in keep:
            out.append("0 " + " ".join(s[1:]))
    return out


def pairs(img_dir, lab_dir):
    for p in sorted(Path(img_dir).iterdir()):
        if p.suffix.lower() in IMG:
            yield p, Path(lab_dir) / (p.stem + ".txt")


def main():
    random.seed(0)
    test_hashes = []
    for d in ("ext", "rdd"):
        for p in (ROOT / "data" / "eval_pothole" / d / "images").iterdir():
            h = dhash(p)
            if h is not None:
                test_hashes.append(h)
    print("test hashes", len(test_hashes))

    def leaks(p):
        h = dhash(p)
        return h is None or any(bin(h ^ t).count("1") <= 4 for t in test_hashes)

    sets = {"train": [], "val": []}

    # RDD2022 (our split: holdout val list from data/merged)
    merged_val = set(Path(x).name for x in (ROOT / "data/merged/val.txt").read_text().split())
    rdd = RAW / "rdd2022" / "train"
    negs = []
    for img, lab in pairs(rdd / "images", rdd / "labels"):
        L = read_labels(lab, {3})
        split = "val" if img.name in merged_val else "train"
        if L:
            sets[split].append((img, L, "rdd"))
        elif split == "train":
            negs.append(img)
    random.shuffle(negs)
    sets["train"] += [(p, [], "rddneg") for p in negs[:2000]]

    py = RAW / "potholes_yolov8" / "train"
    sets["train"] += [(i, read_labels(l, {0}), "py") for i, l in pairs(py / "images", py / "labels")]
    mk = RAW / "pot_muskan"
    sets["train"] += [(i, read_labels(l, {0}), "mk") for i, l in pairs(mk / "train/images", mk / "train/labels")]
    sets["val"] += [(i, read_labels(l, {0}), "mk") for i, l in pairs(mk / "valid/images", mk / "valid/labels")]
    lz = list(pairs(RAW / "pot_lorenzo/data/images", RAW / "pot_lorenzo/data/labels-YOLO"))
    random.shuffle(lz)
    k = int(len(lz) * 0.85)
    sets["train"] += [(i, read_labels(l, {0}), "lz") for i, l in lz[:k]]
    sets["val"] += [(i, read_labels(l, {0}), "lz") for i, l in lz[k:]]

    for split, items in sets.items():
        d = OUT / split
        (d / "images").mkdir(parents=True, exist_ok=True)
        (d / "labels").mkdir(parents=True, exist_ok=True)
        n = dropped = 0
        stats = {}
        for img, L, src in items:
            if src != "rdd" and src != "rddneg" and leaks(img):  # RDD is split by design; check external sets
                dropped += 1
                continue
            name = f"{src}_{img.stem}{img.suffix.lower()}"
            t = d / "images" / name
            if not t.exists():
                shutil.copy(img, t)
            (d / "labels" / f"{src}_{img.stem}.txt").write_text("\n".join(L) + ("\n" if L else ""))
            n += 1
            stats[src] = stats.get(src, 0) + 1
        print(split, n, "dropped(leak)", dropped, stats)
    (OUT / "data.yaml").write_text(f"path: {OUT.as_posix()}\ntrain: train/images\nval: val/images\n"
                                   f"nc: 1\nnames: ['pothole']\n")
    print("wrote", OUT / "data.yaml")


if __name__ == "__main__":
    sys.exit(main())

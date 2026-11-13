"""Dataset for the road-features model: manhole, speed_breaker, debris, barricade (+ night copies).

Sources:
  - rahul1nexus/road-damage-6-class-yolo-dataset: 2 debris, 3 manhole, 4 speed_breaker, 5 road_barricade
  - david2do/road-anomaly-ds: 1 Speedbump
Images that contain none of these classes are kept as negatives only up to 20% of the set.
"""
import random
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "features"
NAMES = ["manhole", "speed_breaker", "debris", "barricade"]
IMG = {".jpg", ".jpeg", ".png"}


def collect(img_dir, lab_dir, cmap, tag):
    pos, neg = [], []
    if not Path(img_dir).exists():
        return pos, neg
    for p in sorted(Path(img_dir).iterdir()):
        if p.suffix.lower() not in IMG:
            continue
        lab = Path(lab_dir) / (p.stem + ".txt")
        lines = []
        if lab.exists():
            for l in lab.read_text().split("\n"):
                s = l.split()
                if len(s) == 5 and int(float(s[0])) in cmap:
                    lines.append(" ".join([str(cmap[int(float(s[0]))])] + s[1:]))
        (pos if lines else neg).append((p, lines, tag))
    return pos, neg


def main():
    random.seed(0)
    rd6 = {2: 2, 3: 0, 4: 1, 5: 3}
    ra = {1: 1}
    splits = {"train": ([], []), "val": ([], [])}
    for sp, rd_sp, ra_sp in (("train", "train", "train"), ("val", "valid", "val")):
        P, N = splits[sp]
        for pos, neg in (collect(RAW / f"rd6/images/{rd_sp}", RAW / f"rd6/labels/{rd_sp}", rd6, "r6"),
                         collect(RAW / f"road_anomaly/{ra_sp}/images", RAW / f"road_anomaly/{ra_sp}/labels", ra, "ra")):
            P += pos
            N += neg
    for sp, (P, N) in splits.items():
        random.shuffle(N)
        items = P + N[: int(len(P) * 0.25)]
        d = OUT / sp
        (d / "images").mkdir(parents=True, exist_ok=True)
        (d / "labels").mkdir(parents=True, exist_ok=True)
        for img, lines, tag in items:
            name = f"{tag}_{img.stem}"
            t = d / "images" / (name + img.suffix.lower())
            if not t.exists():
                shutil.copy(img, t)
            (d / "labels" / (name + ".txt")).write_text("\n".join(lines) + ("\n" if lines else ""))
        print(sp, "positives", len(P), "images written", len(items))
    (OUT / "data.yaml").write_text(f"path: {OUT.as_posix()}\ntrain: train/images\nval: val/images\n"
                                   f"nc: {len(NAMES)}\nnames: {NAMES}\n")


if __name__ == "__main__":
    main()

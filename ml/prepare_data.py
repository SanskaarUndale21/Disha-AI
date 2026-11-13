"""Build the merged training set (data/merged) from downloaded datasets.

Sources (download with ml/download_data.py):
  - RDD2022 YOLO (sreekaraditya/rdd2022-yolo-crackscan-v2): 4 classes D00/D10/D20/D40
  - Potholes YOLOv8 (anggadwisunarto/potholes-detection-yolov8): single-class potholes, train -> our train,
    valid -> external pothole test set (data/merged/potholes_ext.yaml)
  - RDD2022 India pothole subset (vidishbijalwan/rdd2022-india-pothole-d40): Pascal VOC, converted to YOLO,
    added to train only when the image is not already in RDD2022 (filename check, avoids test leakage)

Uses image-list .txt files (no copying): Ultralytics maps .../images/x.jpg -> .../labels/x.txt.
"""
import random
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "merged"
NAMES = ["longitudinal_crack", "transverse_crack", "alligator_crack", "pothole"]
VOC_MAP = {"D00": 0, "D10": 1, "D20": 2, "D40": 3}
IMG_EXT = {".jpg", ".jpeg", ".png"}


def list_split(base: Path, split: str):
    d = base / split / "images"
    return sorted(p for p in d.iterdir() if p.suffix.lower() in IMG_EXT) if d.exists() else []


def convert_voc(src: Path, dst: Path, skip_names: set):
    img_dir, lab_dir = dst / "images", dst / "labels"
    img_dir.mkdir(parents=True, exist_ok=True)
    lab_dir.mkdir(parents=True, exist_ok=True)
    out = []
    for x in sorted((src / "annotations" / "xmls").glob("*.xml")):
        r = ET.parse(x).getroot()
        fn = r.find("filename").text
        if fn in skip_names:
            continue
        img = src / "images" / fn
        if not img.exists():
            continue
        w, h = int(r.find("size/width").text), int(r.find("size/height").text)
        lines = []
        for o in r.findall("object"):
            c = VOC_MAP.get(o.find("name").text.strip())
            if c is None:
                continue
            b = o.find("bndbox")
            x1, y1, x2, y2 = (float(b.find(k).text) for k in ("xmin", "ymin", "xmax", "ymax"))
            lines.append(f"{c} {(x1 + x2) / 2 / w:.6f} {(y1 + y2) / 2 / h:.6f} {(x2 - x1) / w:.6f} {(y2 - y1) / h:.6f}")
        target = img_dir / fn
        if not target.exists():
            target.write_bytes(img.read_bytes())
        (lab_dir / (Path(fn).stem + ".txt")).write_text("\n".join(lines) + ("\n" if lines else ""))
        out.append(target)
    return out


def remap_yolo(src: Path, dst: Path, cmap: dict):
    """Copy a YOLO split with class ids remapped (e.g. single-class pothole set -> our pothole id 3)."""
    (dst / "images").mkdir(parents=True, exist_ok=True)
    (dst / "labels").mkdir(parents=True, exist_ok=True)
    out = []
    for img in sorted((src / "images").iterdir()):
        if img.suffix.lower() not in IMG_EXT:
            continue
        lab = src / "labels" / (img.stem + ".txt")
        lines = []
        if lab.exists():
            for ln in lab.read_text().split("\n"):
                p = ln.split()
                if len(p) == 5 and int(p[0]) in cmap:
                    lines.append(" ".join([str(cmap[int(p[0])])] + p[1:]))
        t = dst / "images" / img.name
        if not t.exists():
            t.write_bytes(img.read_bytes())
        (dst / "labels" / (img.stem + ".txt")).write_text("\n".join(lines) + ("\n" if lines else ""))
        out.append(t)
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rdd = RAW / "rdd2022"
    splits = {s: list_split(rdd, s) for s in ("train", "val", "test")}
    for s, v in splits.items():
        print(s, len(v))
    have = {p.name for v in splits.values() for p in v}

    extra = []
    india = RAW / "india_d40" / "train"
    if india.exists():
        extra = convert_voc(india, ROOT / "data" / "extra" / "india_d40", have)
        print("india extra (not already in RDD2022):", len(extra))
    pot = RAW / "potholes_yolov8"
    pot_val = []
    if pot.exists():
        pot_train = remap_yolo(pot / "train", ROOT / "data" / "extra" / "potholes_yolov8" / "train", {0: 3})
        pot_val = remap_yolo(pot / "valid", ROOT / "data" / "extra" / "potholes_yolov8" / "valid", {0: 3})
        extra += pot_train
        print("pothole dataset train:", len(pot_train), "external pothole test:", len(pot_val))
        (OUT / "potholes_ext.txt").write_text("\n".join(p.resolve().as_posix() for p in pot_val) + "\n")
        (OUT / "potholes_ext.yaml").write_text(
            f"path: {OUT.resolve().as_posix()}\ntrain: potholes_ext.txt\nval: potholes_ext.txt\n"
            f"test: potholes_ext.txt\nnc: {len(NAMES)}\nnames: {NAMES}\n")
    # RDD2022's official test split ships without labels, so: original val -> our test,
    # 10% of the original train (per country, seeded) -> our val
    random.seed(0)
    by_country = {}
    for p in splits["train"]:
        by_country.setdefault(p.name.split("_")[0], []).append(p)
    train, val = [], []
    for c, items in sorted(by_country.items()):
        random.shuffle(items)
        k = max(1, int(len(items) * 0.1))
        val += items[:k]
        train += items[k:]
    train += extra
    random.shuffle(train)
    test = splits["val"]
    print("final train/val/test:", len(train), len(val), len(test))
    for s, items in (("train", train), ("val", val), ("test", test)):
        (OUT / f"{s}.txt").write_text("\n".join(p.resolve().as_posix() for p in items) + "\n")
    (OUT / "data.yaml").write_text(
        f"path: {OUT.resolve().as_posix()}\ntrain: train.txt\nval: val.txt\ntest: test.txt\n"
        f"nc: {len(NAMES)}\nnames: {NAMES}\n")
    print("wrote", OUT / "data.yaml")


if __name__ == "__main__":
    main()

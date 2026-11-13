"""Single-class pothole eval sets (class 0 = pothole) for comparing pothole detectors.

ext  : potholes-yolov8 valid split (396 imgs, not used in any training here)
rdd  : RDD2022 test images (= original val) that contain at least one D40 pothole, other classes dropped
"""
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "eval_pothole"


def build(name, items):
    d = OUT / name
    (d / "images").mkdir(parents=True, exist_ok=True)
    (d / "labels").mkdir(parents=True, exist_ok=True)
    n = 0
    for img, lab in items:
        lines = [" ".join(["0"] + l.split()[1:]) for l in lab.read_text().split("\n") if l.strip().startswith("3 ")]
        if not lines:
            continue
        t = d / "images" / img.name
        if not t.exists():
            shutil.copy(img, t)
        (d / "labels" / (img.stem + ".txt")).write_text("\n".join(lines) + "\n")
        n += 1
    (d / "data.yaml").write_text(f"path: {d.as_posix()}\ntrain: images\nval: images\ntest: images\nnc: 1\nnames: ['pothole']\n")
    print(name, n)


ext = ROOT / "data" / "extra" / "potholes_yolov8" / "valid"
build("ext", [(p, ext / "labels" / (p.stem + ".txt")) for p in sorted((ext / "images").iterdir())])
rdd = ROOT / "data" / "raw" / "rdd2022" / "val"
build("rdd", [(p, rdd / "labels" / (p.stem + ".txt")) for p in sorted((rdd / "images").iterdir())
              if (rdd / "labels" / (p.stem + ".txt")).exists()])

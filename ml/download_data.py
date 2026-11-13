"""Download datasets and the pretrained baseline weights.

needs Kaggle API credentials (~/.kaggle/kaggle.json or access_token).
usage: python ml/download_data.py [--skip-rdd]
"""
import argparse
import subprocess
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
DATASETS = {
    "rdd2022": "sreekaraditya/rdd2022-yolo-crackscan-v2",  # ~12 GB, YOLO format, 4 classes
    "india_d40": "vidishbijalwan/rdd2022-india-pothole-d40",  # ~80 MB, VOC, potholes on Indian roads
}
BASELINE = "https://huggingface.co/dronefreak/rdd2022-yolov8m/resolve/main/best.pt"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-rdd", action="store_true")
    a = ap.parse_args()
    for name, ref in DATASETS.items():
        if a.skip_rdd and name == "rdd2022":
            continue
        dst = RAW / name
        if dst.exists() and any(dst.iterdir()):
            print("exists", dst)
            continue
        subprocess.run(["kaggle", "datasets", "download", ref, "-p", str(dst), "--unzip"], check=True)
    w = ROOT / "models" / "rdd2022_yolov8m.pt"
    if not w.exists():
        w.parent.mkdir(exist_ok=True)
        print("downloading baseline weights ->", w)
        urllib.request.urlretrieve(BASELINE, w)


if __name__ == "__main__":
    main()

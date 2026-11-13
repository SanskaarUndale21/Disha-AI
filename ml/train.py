"""Fine-tune YOLO on the merged road-damage dataset and export models/best.pt.

usage: python ml/train.py --base models/rdd2022_yolov8m.pt --epochs 30 --batch 8
"""
import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=str(ROOT / "models" / "rdd2022_yolov8m.pt"))
    ap.add_argument("--data", default=str(ROOT / "data" / "merged" / "data.yaml"))
    ap.add_argument("--epochs", type=int, default=30)
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--name", default="roadwatch")
    ap.add_argument("--fraction", type=float, default=1.0)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--out", default=str(ROOT / "models" / "best.pt"), help="where to copy best weights")
    ap.add_argument("--patience", type=int, default=10)
    ap.add_argument("--lr0", type=float, default=0.0005)
    a = ap.parse_args()

    from ultralytics import YOLO
    model = YOLO(a.base)
    res = model.train(
        data=a.data, epochs=a.epochs, imgsz=a.imgsz, batch=a.batch, workers=a.workers, device=0,
        project=str(ROOT / "runs" / "train"), name=a.name, exist_ok=True, resume=a.resume, fraction=a.fraction,
        optimizer="AdamW", lr0=a.lr0, cos_lr=True, patience=a.patience, close_mosaic=5, amp=True, cache=False,
        # road imagery: no vertical flips, mild colour jitter for lighting / weather variation
        fliplr=0.5, flipud=0.0, hsv_h=0.015, hsv_s=0.6, hsv_v=0.45, degrees=0.0, scale=0.5, mosaic=1.0,
        mixup=0.05, plots=True,
    )
    best = Path(res.save_dir) / "weights" / "best.pt"
    if best.exists():
        shutil.copy(best, a.out)
        print("copied", best, "->", a.out)


if __name__ == "__main__":
    main()

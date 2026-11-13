"""Where does video analysis time go? Runs detect_video on one sample with cProfile and prints the top costs."""
import cProfile
import glob
import os
import pstats
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
from app import detector  # noqa: E402

name = sys.argv[1] if len(sys.argv) > 1 else "4.06.02"
falls = (sys.argv[2] != "nofalls") if len(sys.argv) > 2 else True
f = next(p for p in glob.glob(os.path.join(ROOT, "samples", "**", "*"), recursive=True) if name in p)
out = os.path.join(ROOT, "backend", "storage", "annotated", "_profile.mp4")
detector._load()
import numpy as _np
detector.infer_batch([_np.zeros((640,640,3),"uint8")]*6); detector.infer_tiles([_np.zeros((720,1280,3),"uint8")])  # warm up like the server
t = time.time()
pr = cProfile.Profile()
pr.enable() if "--prof" in sys.argv else None
rows, meta = detector.detect_video(f, out, None, "2k", None, falls)
pr.disable() if "--prof" in sys.argv else None
dt = time.time() - t
print(f"{os.path.basename(f)}: {meta['frames_processed']} frames in {dt:.1f}s = {meta['frames_processed'] / dt:.1f} fps, tracks={len(rows)}")
if "--prof" in sys.argv:
    pstats.Stats(pr).sort_stats("cumulative").print_stats(18)

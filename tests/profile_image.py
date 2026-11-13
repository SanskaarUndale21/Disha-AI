import cProfile, glob, os, pstats, sys, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
import cv2
from app import detector
f = next(p for p in glob.glob(os.path.join(ROOT, "samples", "**", "*"), recursive=True) if sys.argv[1] in p)
img = cv2.imread(f); print(os.path.basename(f), img.shape)
detector._load(); detector.detect_image(img)  # warm up
t = time.time(); pr = cProfile.Profile(); pr.enable(); rows, meta = detector.detect_image(img); pr.disable()
print(f"detect_image {time.time()-t:.1f}s rows={len(rows)}")
pstats.Stats(pr).sort_stats("cumulative").print_stats(14)

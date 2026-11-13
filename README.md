# RoadWatch AI: Road Damage and Pothole Detection (PS 02)

Upload road photos or dashcam clips, detect potholes and cracks with YOLO, track each defect with a unique ID
across video frames, merge repeat reports of the same defect, score risk, let an admin verify/correct results,
and monitor how each location changes over time.

## Features

| Requirement | How it is done |
|---|---|
| **Real-time detection** | `Live detection` page: phone/webcam camera or a local video streamed over WebSocket (`/ws/live`). Per-session ByteTrack, class-coloured borders with corner brackets (thicker = more severe, glowing = high risk), ID tags like `PH#3`, unconfirmed tracks dashed. Live FPS / latency / unique counts; "Save session" pushes the unique defects into the registry (with dedup) |
| **Voice helpline** | Sarvam voice agent "RoadWatch Pothole Helpline" (English + Hindi): greets the caller, asks if they want to report a pothole, confirms the complaint is noted. Agent id `RoadWatch-P-c22eb265-2f9b` |
| Upload images / videos | Drag and drop or phone camera capture (`Analyze` page) |
| Detect potholes and other damage | YOLOv8m fine-tuned on RDD2022 (+ Indian pothole data): longitudinal crack D00, transverse crack D10, alligator crack D20, pothole D40 |
| Bounding boxes | Annotated image / H.264 video with class, confidence, severity and defect ID |
| Severity | Low / Medium / High from physical extent per class (area ratio for potholes and alligator cracks, major axis length for linear cracks), confidence weighted |
| Location metadata | Fallback chain: photo EXIF GPS, then GPX track (per-frame interpolation for video, adjustable time offset), then manual map pin, else `unknown` (never faked) |
| Reports | CSV register, PDF summary, per-inspection PDF |
| Counts and categories, dashboard | KPIs, category / risk charts, activity timeline, Leaflet map coloured by risk |
| 1. Unique pothole tracking | Ultralytics ByteTrack on every frame; tracks shorter than 3 frames dropped as flicker; one record per track with its best frame crop |
| 2. Duplicate report detection | Whole-image dHash (same photo uploaded twice) + per-defect matching: haversine radius (15 m, 30 m for manual pins) AND DINOv2 ViT-S/14 crop embedding cosine >= 0.75 (0.85 when no GPS). Matches are merged into the existing defect instead of creating a new record |
| 3. Risk score | `100*(0.45*severity + 0.25*class_hazard + 0.30*road_factor) + repeat bonus + worsening bonus`, bands High >= 70, Medium >= 40. Road factor from road type and traffic level supplied at upload (unknown = neutral, not invented) |
| 4. Manual verification | Verification queue: confirm, reject (false positive), correct class / severity, with note and audit fields. Verified labels export as a YOLO dataset zip for re-training |
| 5. Progress monitoring | Each defect keeps a timeline; re-sightings are classified worsening / improving / stable by severity change; defects not seen again by a later geotagged inspection at the same spot are flagged repaired. Location compare view shows first vs latest inspection verdict |
| Evaluation | `ml/evaluate.py`: precision, recall, F1, mAP@50, mAP@50-95 per class + confusion matrix, shown on the `Model` page |

## Accuracy work (models)

| Component | Model | Notes |
|---|---|---|
| Pothole specialist | YOLO11m, fine-tuned here from PotholeNet | trained on RDD2022 potholes + 5 public pothole sets (about 9,400 pothole images); near duplicates of test images removed by perceptual hash |
| Cracks | YOLOv8m RDD2022 (D00, D10, D20) | public checkpoint |
| Road features | YOLO11s trained here | manhole, speed breaker, debris, barricade (only used at confidence 0.5 and above) |
| Upload mode | Weighted Boxes Fusion of two pothole models + horizontal-flip test-time augmentation | approach used by the CRDDC2022 winners |

Held-out pothole tests (mAP50): public RDD2022 model 2%, PotholeNet 74%, fine-tuned 77% on the external set; on hard RDD2022 potholes 18% (PotholeNet) to 46% (fine-tuned).

**All-weather robustness.** `ml/add_conditions.py` makes photometric copies with night, fog (atmospheric scattering model), smoke, dust, rain streaks and motion blur. Training mixes them in, and `ml/eval_conditions.py` scores each model per condition on held-out copies of the test set.

**Severity scale.** Minor / Moderate / Severe / Critical, cut at the 35th / 70th / 90th percentile of 2,400 real potholes measured by the OpenCV analyser (size corrected for distance, depth contrast, edge roughness), plus a water-filled flag.

**Thermal guard.** `ml/thermal_guard.py` pauses training when the laptop GPU reaches 80 C and resumes after a 3 minute cool-down.

## Operations

- Repair cost estimate per defect (area, depth by severity, cold or hot mix, labour, traffic management, 10% contingency; all rates are configurable assumptions) and a budget planner (0/1 knapsack maximising risk removed within a budget).
- Alerts: high risk, new defect, repeat report, getting worse, repaired, needs review, problem road, overdue repair, rain risk (Open-Meteo forecast).
- Road type from OpenStreetMap (Overpass), cached; feeds the risk score.
- Citizen complaint PDF and authority report PDF with QR tracking codes; mock "send to roads department".
- Voice helpline (Sarvam): 11 Indian languages, collects issue, road, landmark, city, danger and duration, ends silent calls after 8 seconds. Phone complaints are geocoded and move up a verification ladder: unverified, corroborated (AI detection nearby or a second caller), photo verified (citizen opens the upload link, GPS captured automatically), field verified (patrol or officer).

## Research notes / choices

* **Dataset**: RDD2022 (CRDDC 2022, 6 countries incl. India) in YOLO format, 4 main damage classes. Extra
  Indian pothole annotations are merged into training only when not already part of RDD2022 (filename check)
  so the test split stays clean.
* **Model**: starting point is the public `dronefreak/rdd2022-yolov8m` checkpoint (reported mAP@50 0.62 on
  its test split). It missed potholes on Indian road images in testing, so it is fine-tuned further on the merged
  set (`ml/train.py`). The app automatically uses `models/best.pt` when present, else the baseline.
* **Duplicate matching**: calibrated on RDD2022 India crops (same defect under crop shift, scale, brightness, blur
  versus different defects). ResNet18 ImageNet features reached only TPR 0.70 at FPR 0.55%; SIFT + RANSAC failed on
  low-texture asphalt; DINOv2 ViT-S/14 gave TPR 0.87 at FPR 0.45% (cos 0.80), so it is used, gated by GPS radius.
* **Preprocessing**: CLAHE on the L channel only for dark or low-contrast frames.

## Run

Requirements: Python 3.12+, Node 20+, NVIDIA GPU optional (CPU works, slower).

```bash
python -m venv .venv
.venv/Scripts/pip install torch torchvision --index-url https://download.pytorch.org/whl/cu130
.venv/Scripts/pip install -r backend/requirements.txt

# data + baseline weights (Kaggle credentials needed for datasets)
.venv/Scripts/python ml/download_data.py
.venv/Scripts/python ml/prepare_data.py

# optional: fine-tune, then evaluate (writes models/best.pt, models/metrics.json)
.venv/Scripts/python ml/train.py --epochs 30 --batch 8
.venv/Scripts/python ml/evaluate.py --weights models/best.pt

# backend (http://127.0.0.1:8000, API docs at /docs)
cd backend && ../.venv/Scripts/python -m uvicorn app.main:app --port 8000

# frontend (http://localhost:5173)
cd frontend && npm install && npm run dev
```

`npm run build` in `frontend/` produces `frontend/dist`, which the backend then serves at `/` (single server).

## Layout

```
backend/app/   FastAPI app: detector (YOLO + ByteTrack), pipeline (dedup, registry, progress),
               scoring (severity, risk), geo (EXIF, GPX, haversine), similarity (DINOv2, dHash), reports
frontend/src/  React + Vite: Dashboard, Analyze, Defect registry, Verification, Progress, Inspections, Model
ml/            download_data, prepare_data, train, evaluate
models/        weights + metrics.json (weights are not committed)
```

Configuration via env vars (`RD_CONF`, `RD_DUP_RADIUS_M`, `RD_DUP_SIM`, `RD_WEIGHTS`, ...), see `backend/app/config.py`.

Disclaimer: risk scores support prioritisation; they do not replace an engineer's site inspection.
Ultralytics YOLO is AGPL-3.0.

## Acknowledgements

- RDD2022 / CRDDC2022 road damage data and challenge write-ups (sekilab, University of Tokyo).
- Public pothole datasets on Kaggle and Roboflow Universe (Chitholian / Roboflow pothole set, road-anomaly, potholes-detection-yolov8 and others) used for fine-tuning.
- PotholeNet (YOLO11m, Indian roads) as the starting checkpoint for the pothole specialist.
- Product ideas for citizen drive mode, jurisdiction routing and the public map were inspired by
  [coding-parrot/pothole-reporter](https://github.com/coding-parrot/pothole-reporter) (MIT). No code was copied; RoadWatch implements them in its own Flutter / FastAPI stack with its own detection models.

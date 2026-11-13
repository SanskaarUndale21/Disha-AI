# AI Road Damage and Pothole Detection - Complete Project Guide

# Required Features Checklist (PS 02: AI Road Damage Detection)

## Core features
- [ ] Upload road images (jpg/png) and video clips (mp4)
- [ ] Detect potholes and other damage classes (D00 longitudinal, D10 transverse, D20 alligator, D40 pothole)
- [ ] Draw bounding boxes (or segmentation masks) on output
- [ ] Classify severity: Low / Medium / High
- [ ] Capture location metadata (EXIF GPS, GPX upload, or manual lat/long entry)
- [ ] Generate road-damage report (PDF/CSV)
- [ ] Display defect counts per category
- [ ] Dashboard of analyzed road samples (table, charts, map)

## Mandatory advanced features
1. **Unique pothole tracking**
   - [ ] ByteTrack / BoT-SORT, persistent track IDs
   - [ ] Count unique IDs, not per-frame detections
   - [ ] Show raw detections vs unique count in the UI
2. **Duplicate report detection**
   - [ ] GPS proximity check (e.g. < 10 m)
   - [ ] Image similarity (perceptual hash or CNN embedding cosine similarity)
   - [ ] Flag likely duplicates for admin merge, do not create a new record
3. **Road damage risk prediction**
   - [ ] Documented formula, e.g. `risk = 0.4*severity + 0.2*type_weight + 0.2*road_importance + 0.2*recurrence`
   - [ ] Road type from OpenStreetMap (free)
   - [ ] Highlight high-risk defects in red
4. **Manual verification and correction**
   - [ ] Admin page: Confirm / Reject / Edit class and severity
   - [ ] Save verified results separately from raw AI output
   - [ ] Keep an audit trail (who, when, what changed)
5. **Progress monitoring**
   - [ ] Store inspection date and location for every sample
   - [ ] Match defects at the same location across dates
   - [ ] Label each: Worsening / Improved / Repaired / New
   - [ ] Timeline view per location

## Technical expectations
- [ ] YOLOv8 / YOLO11 (or SSD equivalent), pretrained then fine-tuned on RDD2022
- [ ] Preprocessing: resize, CLAHE/low-light enhancement, augmentation
- [ ] Video object tracking
- [ ] Evaluation: precision, recall, F1, mAP@0.5, mAP@0.5:0.95 (per class)
- [ ] Confusion matrix and PR curve in the report
- [ ] Database storing inspections, defects, locations, verification status

## Deliverable
- [ ] Working app: detect, track, verify, monitor, report
- [ ] Demo video/dataset prepared
- [ ] Metrics table and limitations documented

---

# Alerts Specification

## Alert types

| # | Alert | Trigger | Audience | Channel |
|---|-------|---------|----------|---------|
| 1 | High-risk defect | risk score >= 0.75 | Admin / authority | Dashboard banner, email (mock) |
| 2 | New pothole detected | Verified new defect, no duplicate found | Admin | Dashboard notification |
| 3 | Duplicate report | Same location/image similarity above threshold | Admin | Merge-review queue |
| 4 | Worsening defect | Area/severity grew vs previous inspection | Admin / authority | Dashboard, report highlight |
| 5 | Repair confirmed | Defect no longer detected at same location | Admin | Status change to Repaired |
| 6 | Low-confidence detection | Model confidence < 0.4 | Verifier | Verification queue (active learning) |
| 7 | Repeat offender road | 3+ defects on the same road segment | Authority | Weekly summary |
| 8 | Overdue repair | Verified defect unrepaired > N days | Authority | Dashboard, escalation |
| 9 | Weather risk | Heavy rain forecast near open high-risk defects (Open-Meteo) | Authority | Dashboard |
| 10 | Live dashcam warning | Pothole detected ahead in live mode | Driver | On-screen text + beep ("Pothole ahead") |

## Severity levels
- **Critical**: risk >= 0.75 (red)
- **Warning**: 0.5 to 0.75 (orange)
- **Info**: below 0.5 (blue)

## Rules
- Alerts are deduplicated: one alert per defect per state change
- Every alert stores: id, type, defect id, location, timestamp, status (Open / Acknowledged / Resolved)
- Admin can acknowledge or resolve alerts
- No paid API needed: email/SMS are mock outputs (logged and shown as a generated message)

## Example message
> HIGH RISK: Pothole #P-0142 on MG Road (12.9716, 77.5946). Severity: High, risk 0.82. First reported 2026-11-01, worsened since last inspection. Estimated repair cost: Rs 4,500.

---

# Unique Features (to impress judges)

## Recommended combination
1. Repair cost estimator and budget optimizer
2. Pothole depth/volume estimation (monocular depth)
3. Safe-route navigation or citizen portal
4. Night/rain robustness (cheap metrics win)

## Full list
- [ ] **Repair cost and budget optimizer**: area x depth x material rate; knapsack picks best roads to fix within a budget
- [ ] **Depth and volume estimation**: Depth Anything / MiDaS on pothole crop, calibrated with lane width
- [ ] **Risk by vehicle type**: two-wheeler vs car, adjusted for night and waterlogging
- [ ] **Predictive deterioration**: forecast crack to pothole using inspection history plus rainfall (Open-Meteo)
- [ ] **Live heatmap and citizen portal**: Leaflet map, status flow Reported > Verified > Scheduled > Repaired, ticket IDs
- [ ] **Safe-route navigation**: OSMnx graph, safest vs fastest route
- [ ] **Real-time dashcam mode**: webcam/phone stream with "Pothole ahead" alert
- [ ] **Night and rain robustness**: CLAHE / Zero-DCE, before/after metrics table
- [ ] **Explainability**: Grad-CAM, auto-flag low-confidence for review (active learning)
- [ ] **Auto complaint generator**: formatted complaint with photo, location, severity, cost (mock send)

## Extra defect classes beyond RDD2022
- Faded or missing lane markings
- Sunken or open manholes and drain covers
- Speed breakers / unmarked bumps
- Waterlogging
- Edge and shoulder erosion
- Rutting and patch repairs
- Loose gravel and debris
- Damaged signs

Tip: train the 4 RDD2022 classes well first, then add 2 or 3 extras from Roboflow Universe datasets.

## Presentation framing
Pipeline: **Detect > Track > Quantify > Prioritize > Repair > Monitor**
Show numbers: mAP, duplicates removed, cost estimate, unique vs raw count.

---

# Build Plan and Tech Stack

## Stack
- Model: Ultralytics YOLOv8/YOLO11 (nano or small), ByteTrack/BoT-SORT
- Backend: FastAPI (or Streamlit for fastest demo)
- DB: SQLite (upgrade to PostgreSQL if needed)
- Frontend: Streamlit or React + Leaflet
- Maps: OpenStreetMap, Folium/Leaflet, OSMnx
- Charts: Plotly
- Reports: ReportLab or WeasyPrint
- Similarity: imagehash or ResNet embeddings
- Dataset: RDD2022 (India, Japan, Czech subsets)

## Suggested order
1. **Data and model**: download RDD2022, convert to YOLO format, train, record metrics
2. **Inference app**: upload image/video, boxes, severity
3. **Tracking**: unique IDs on video, unique vs raw counts
4. **Database and location**: EXIF GPS, GPX, manual entry; store inspections
5. **Duplicate detection**: GPS radius plus image hash/embedding
6. **Risk score**: formula plus OSM road type, red highlighting
7. **Admin verification page**: confirm, reject, edit, audit trail
8. **Progress monitoring**: match by location, Worsening/Improved/Repaired
9. **Alerts**: see 02_alerts.md
10. **Dashboard and PDF report**
11. **Unique features**: pick 2 or 3 from 03_unique_features.md
12. **Polish**: demo data, rehearsed demo path, metrics table, limitations

## Database tables (starter)
- `inspections(id, date, source_file, lat, lon, notes)`
- `defects(id, inspection_id, track_id, class, severity, confidence, bbox, area, risk, status, location_id)`
- `locations(id, lat, lon, road_name, road_type)`
- `verifications(id, defect_id, admin, action, old_value, new_value, timestamp)`
- `alerts(id, type, defect_id, level, message, status, created_at)`

## Evaluation checklist
- Precision, recall, F1, mAP@0.5, mAP@0.5:0.95 per class
- Confusion matrix, PR curve
- Before/after table for preprocessing (night/blur)
- Duplicate detection accuracy on a small labelled set

## Demo checklist
- Video with clear potholes plus a repeat pass of the same stretch (for progress monitoring)
- One end-to-end path rehearsed
- Honest slide on limitations

---


# Report Specification

The system generates two reports per defect (and a combined batch version per inspection): a **User Complaint Report** and an **Admin / Authority Report**. Output as PDF (ReportLab/WeasyPrint) plus CSV for the batch.

## 1. User Complaint Report (citizen-facing)

Purpose: a ready-to-submit complaint to the municipal body.

| Section | Contents |
|---------|----------|
| Header | Complaint ID / ticket number, date and time, report status (Reported / Verified / Scheduled / Repaired) |
| Pothole image | Original photo plus annotated image with bounding box or mask |
| Location | Latitude/longitude, address or nearest road name, landmark, map snapshot (OpenStreetMap), source of location (EXIF / GPX / manual) |
| Damage details | Damage type (pothole, longitudinal/transverse/alligator crack), severity (Low/Medium/High), approximate size, detection confidence |
| Safety note | Risk level (e.g. "High risk: busy road, two-wheeler hazard"), waterlogged or night-visibility remarks if any |
| Reporter details | Name, phone/email (optional), date reported |
| Duplicate check | "New report" or "Matches existing complaint #ID, your report was added as supporting evidence" |
| Description | Auto-generated complaint text, editable by the user |
| Tracking | Ticket ID and status link/QR so the user can follow progress |

Sample auto text:
> Complaint #C-0142: A High-severity pothole was detected on MG Road near City Mall (12.9716, 77.5946) on 13 Nov 2026. It is a risk to two-wheelers and cars. Please inspect and repair. Photo attached.

## 2. Admin / Authority Report (internal)

Purpose: decision support for the repair team and the verifier.

| Section | Contents |
|---------|----------|
| Header | Defect ID, track ID, linked complaint IDs, inspection date, inspector/admin, verification status (AI-detected / Confirmed / Rejected / Corrected) |
| Images | Original, annotated, depth/volume view if available, previous-inspection image for comparison |
| Location | Coordinates, road name, road type (highway / arterial / residential from OSM), ward/zone, map pin |
| AI details | Class, confidence, model version, bounding box, area (cm2 or % of frame) |
| Verification log | Who confirmed/rejected/edited, what changed, timestamp |
| Severity and risk | Severity level, risk score with formula breakdown (severity, type weight, road importance, recurrence), High-risk flag |
| **Repair cost estimate** | Area, estimated depth, volume, material (cold mix / hot mix / patch), material cost, labour cost, equipment/traffic management cost, **total estimated cost** |
| Repair priority | Priority rank, recommended repair deadline, whether it fits within the chosen budget (budget optimizer) |
| Duplicate info | Merged duplicate count, number of citizen reports for the same pothole |
| Progress history | Timeline of past inspections: Worsening / Improved / Repaired / New, with area change and dates |
| Alerts | Active alerts for this defect (high risk, overdue, weather risk) |
| Action | Assigned team, status (Open / Scheduled / In progress / Repaired), repair date, post-repair photo |

### Repair cost formula (simple, documented)

```
area_m2     = pixel_area * (m_per_pixel ^ 2)      # calibrated by lane width or reference object
volume_m3   = area_m2 * depth_m                   # depth from depth model or severity default
material    = volume_m3 * rate_per_m3             # e.g. cold mix / hot mix rate
labour      = fixed_per_pothole + area_m2 * labour_rate
traffic_eq  = road_type_factor * base_charge      # highway > arterial > residential
total_cost  = (material + labour + traffic_eq) * (1 + contingency)   # e.g. 10%
```

Default depth if no depth model: Low 2 cm, Medium 5 cm, High 8 cm. All rates are configurable in a settings file and should be labelled as assumptions, not official government rates.

## 3. Batch / Inspection Summary Report (admin)

- Inspection ID, date, route/area, total frames or images processed
- Raw detections vs **unique defects** after tracking and duplicate removal
- Counts by category and by severity (table and charts)
- High-risk defects list (top 10) with images and locations
- **Total estimated repair cost** and cost by road/zone
- Budget optimizer result: which defects to fix within budget X
- Comparison with the previous inspection: new, worsened, improved, repaired counts
- Map with all defects colour-coded by severity
- Model metrics section (precision, recall, F1, mAP) for transparency

## 4. Report features to build
- [ ] Generate PDF per defect (user version and admin version)
- [ ] Generate batch PDF and CSV per inspection
- [ ] Embed images (original and annotated) and a map snapshot
- [ ] Unique complaint/ticket ID plus QR code for status tracking
- [ ] Download buttons in dashboard and verification page
- [ ] Mock "send to authority" action (logs and shows the email text)
- [ ] Reports reflect verified data (admin corrections), not only raw AI output


# Detailed Feature Notes and Implementation Tips

## A. Required features: how to build each

**Model and training**
- Use YOLOv8 or YOLO11 (Ultralytics). Start from pretrained weights, fine-tune on RDD2022, use the nano or small model for speed.
- RDD2022 subsets: India (most relevant), Japan, Czech.
- Report precision, recall, F1, mAP@0.5 and mAP@0.5:0.95 per class, plus confusion matrix and PR curve (Ultralytics prints these).
- Augmentation: brightness, blur, shadows, since real road footage is noisy.

**Severity classification**
- Simple: severity = bounding-box or mask area as a fraction of the frame, then Low / Medium / High thresholds.
- Better: use segmentation (YOLOv8-seg) for real area, and weight by damage type (alligator cracks score higher than thin cracks).

**Unique pothole tracking**
- ByteTrack or BoT-SORT, built into Ultralytics: `model.track(persist=True)`.
- Count unique track IDs, not detections per frame.

**Duplicate report detection**
- Combine GPS distance (e.g. under 10 m) with image similarity (perceptual hash, or CNN embeddings with cosine similarity).
- If either signal says "same pothole", flag it for the admin to merge instead of creating a new record.

**Location without GPS hardware**
- Read EXIF GPS from photos.
- For videos: upload a GPX file, or enter start and end coordinates and interpolate along the route.
- Maps: free OpenStreetMap tiles with Leaflet or Folium.

**Risk score**
- Keep the formula clear: `risk = 0.4*severity + 0.2*type_weight + 0.2*road_importance + 0.2*recurrence`.
- Road importance from OSM road type (highway, arterial, residential) via the free Overpass API.
- Show the formula in the UI and highlight anything above the threshold in red.

**Admin verification**
- Review page with image, boxes, and Confirm / Reject / Edit-class buttons.
- Save verified data separately and reuse it to retrain the model (human-in-the-loop).

**Progress monitoring**
- Store each inspection with date and location, match defects by location and similarity.
- Label: Worsening (area grew), Improved, Repaired (no longer detected), New.
- Timeline per location.

## B. Extra damage and road-condition classes to detect

From RDD2022 (free labels):
- **D00 Longitudinal cracks**: along the road
- **D10 Transverse cracks**: across the road
- **D20 Alligator cracks**: web of cracks, structural failure sign
- **D40 Potholes**: main target

Extras (other datasets or self-labelling, e.g. Roboflow Universe):
- Faded or missing lane markings
- Sunken or open manholes and drain covers
- Speed breakers and unmarked bumps (night hazard)
- Waterlogging and puddles (hide potholes, flag drainage issues)
- Edge or shoulder erosion
- Rutting and patch repairs (patches help repair tracking)
- Debris, loose gravel, fallen objects
- Missing or damaged road signs and cat's-eyes

Advice: train the 4 RDD2022 classes well first, then add 2 or 3 extras (manholes, waterlogging, faded lane markings are good picks).

## C. Unique features in detail

| # | Feature | How it works | Pitch |
|---|---------|--------------|-------|
| 1 | Repair cost and budget optimizer | Severity and area give a cost estimate (area x depth x material rate); a knapsack picks the best set of roads to fix | "Given a budget of Rs X, here is the optimal set of roads to fix." |
| 2 | Depth and volume estimation | Monocular depth model (Depth Anything or MiDaS, free) on the pothole crop, calibrated with lane width | Real severity (volume) instead of box area |
| 3 | Risk by vehicle type | Separate risk for two-wheeler, car, truck; add time-of-day and waterlogging factors | Same pothole is more dangerous to a two-wheeler |
| 4 | Predictive deterioration | Regression over inspection history plus rainfall (Open-Meteo, free) predicts crack to pothole | "We fix it before it fails." |
| 5 | Live heatmap and citizen portal | Leaflet danger heatmap with filters; citizens upload a photo, get a ticket ID, track status; duplicate detection blocks spam | Public usefulness |
| 6 | Safe-route navigation | OSMnx road graph, rank routes by pothole risk | Safest vs fastest route demo |
| 7 | Real-time dashcam mode | Webcam or phone stream with on-screen "Pothole ahead, 20 m" alert | Strong stage demo |
| 8 | Night and rain robustness | CLAHE or Zero-DCE low-light enhancement, before/after metrics table | Measured gain |
| 9 | Explainability | Grad-CAM or confidence heatmaps; auto-flag low-confidence detections for admin review (active learning) | Trustworthy AI |
| 10 | Auto complaint generator | One click builds a complaint with location, photo, severity, cost; mock send to authority | Closes the loop |

Recommended combination: #1 repair cost and budget optimizer, #2 depth/volume, #6 safe-route or #5 citizen portal, plus #8 as a cheap metrics win.

## D. Stack suggestion
- Streamlit for the fastest working demo, or FastAPI with React for a polished UI
- SQLite or PostgreSQL
- Plotly for dashboard charts
- ReportLab or WeasyPrint for PDF reports

## E. Demo and presentation tips
- Prepare a short video with clear potholes and a second pass over the same stretch weeks apart (or simulated) so progress monitoring shows an obvious result.
- Show before/after tracking so the unique count is visibly lower than the raw detection count.
- Prepare the metrics table in advance and be honest about limitations.
- Frame the project as a pipeline: detect, track, quantify, prioritize, repair, monitor.
- Show numbers: mAP, cost saved, percent of duplicates removed.
- Rehearse one end-to-end demo path instead of many half-working features.

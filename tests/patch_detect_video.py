"""One-off patch: rewrite detect_video to read frames in chunks, run detection batched, and pace the fall check."""
p = r"D:\coding\Hackvalley\backend\app\detector.py"
s = open(p, encoding="utf-8").read()
i = s.index("def detect_video(path, out_path")
j = s.index("def hud(img, unique, by_class):")
new = '''VIDEO_BATCH = int(os.getenv("RD_VIDEO_BATCH", "6"))


def detect_video(path, out_path, frame_cb=None, quality="2k", classes=None, falls=True):
    """Track defects through a video. Returns (unique track rows, meta). Annotated H.264 video is written.

    Speed: frames are read in chunks and run through the detector as one batch (far faster than frame by frame);
    magnified tiles that find distant potholes run on every third frame (every second in 4K); the person/fall check
    runs about 8 times per second. Every frame is analysed (stride 1) so tracks and confidence accumulate."""
    import imageio.v2 as iio

    cap = cv2.VideoCapture(str(path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    stride = max(1, config.VIDEO_FRAME_STRIDE)
    writer = iio.get_writer(str(out_path), fps=fps / stride, codec="libx264", quality=7, macro_block_size=8,
                            ffmpeg_log_level="error", pixelformat="yuv420p")
    quality = normalize_quality(quality)
    cfg = VIDEO_QUALITY[quality]
    tile_every = 2 if quality == "4k" else 3
    tk = Tracker(imgsz=cfg["imgsz"], far=cfg["far"], allow=classes)
    idx = processed = 0
    t0 = time.time()
    fm, fall_list, last_pose = None, [], -1.0
    safety = None
    if falls:
        try:
            from . import safety
            fm = safety.FallMonitor()
        except Exception as e:
            print(f"[video] fall monitor unavailable: {e!r}")
            fm = None
    far_held = None

    def read_chunk():
        nonlocal idx
        chunk = []
        while len(chunk) < VIDEO_BATCH:
            ok, frame = cap.read()
            if not ok:
                break
            if idx % stride:
                idx += 1
                continue
            if processed + len(chunk) >= config.VIDEO_MAX_FRAMES:
                break
            fh, fw = frame.shape[:2]
            if max(fh, fw) > cfg["max_side"]:
                sc = cfg["max_side"] / float(max(fh, fw))
                frame = cv2.resize(frame, (int(fw * sc) // 2 * 2, int(fh * sc) // 2 * 2), interpolation=cv2.INTER_AREA)
            chunk.append((idx, frame))
            idx += 1
        return chunk

    try:
        while True:
            chunk = read_chunk()
            if not chunk:
                break
            procs = [preprocess(f)[0] for _, f in chunk]
            dets = infer_batch(procs, conf_floor=0.1, imgsz=cfg["imgsz"])
            want = [k for k, (n, _) in enumerate(chunk) if (n // stride) % tile_every == 0] if FAR_PASS else []
            if want:
                far_res = infer_tiles([procs[k] for k in want], imgsz=cfg["imgsz"], mode="far")
                far_by = dict(zip(want, far_res))
            else:
                far_by = {}
            for k, (n, frame) in enumerate(chunk):
                if k in far_by:
                    far_held = far_by[k]
                d = dets[k]
                if far_held is not None and len(far_held):
                    d = merge_dets(d, far_held)
                rows = tk.step(procs[k], time_s=n / fps, dets=d)
                shown = [r for r in rows if r["confirmed"]]
                ann = draw(frame, shown, label_track)
                hud(ann, len(tk.unique()), tk.by_class())
                t_s = n / fps
                if fm is not None and (t_s - last_pose >= 0.12 or last_pose < 0):
                    last_pose = t_s
                    try:
                        pots = [(r["track_id"], [r["x1"], r["y1"], r["x2"], r["y2"]]) for r in shown
                                if r.get("class_name") == "pothole" and r.get("track_id") is not None]
                        people, evs = fm.observe(t_s, safety.detect_people(frame), pots)
                        tk.people_last = people
                        for ev in evs:
                            url = safety.snapshot(ann, ev)
                            em = safety.record_emergency(ev, url)
                            fall_list.append({"id": em["id"], "time_s": round(t_s, 1), "snapshot_url": url, "message": em["message"]})
                    except Exception as e:
                        print(f"[video] fall check failed: {e!r}")
                for pp in getattr(tk, "people_last", []) or []:
                    x1, y1, x2, y2 = [int(v) for v in pp["box"]]
                    col = (48, 59, 255) if pp["fallen"] else (255, 255, 255)
                    cv2.rectangle(ann, (x1, y1), (x2, y2), col, 3 if pp["fallen"] else 1)
                    if pp["fallen"]:
                        cv2.putText(ann, "PERSON DOWN", (x1, max(18, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.8, col, 2, cv2.LINE_AA)
                writer.append_data(cv2.cvtColor(ann, cv2.COLOR_BGR2RGB))
                processed += 1
            if frame_cb and total:
                frame_cb(min(1.0, idx / total))
    finally:
        cap.release()
        writer.close()
    out = tk.final_rows()
    meta = {"fps": fps, "frames_total": total, "frames_processed": processed, "width": tk.w, "height": tk.h,
            "raw_track_ids": len(tk.tracks), "quality": quality, "falls": fall_list, "ms": int((time.time() - t0) * 1000)}
    return out, meta


'''
s = s[:i] + new + s[j:]
# consensus confidence tier: a defect seen again and again is more trustworthy than one lucky frame
a = '''            b.update(crop=tr["crop"], frames_seen=tr["hits"], track_id=self.display.get(tid, tid))'''
assert a in s
s = s.replace(a, '''            b.update(crop=tr["crop"], frames_seen=tr["hits"], track_id=self.display.get(tid, tid))
            if b.get("tier") != "high" and tr["hits"] >= 6 and float(b.get("confidence") or 0) >= 0.32:
                b["tier"] = "high"  # seen in many frames: repeat sightings count as confirmation''', 1)
open(p, "w", encoding="utf-8", newline="\n").write(s)
print("patched")

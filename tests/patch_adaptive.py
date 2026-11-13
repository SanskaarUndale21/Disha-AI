"""One-off patch: adaptive frame sampling in detect_video (sparse while the road is clear, dense once damage is seen)."""
p = r"D:\coding\Hackvalley\backend\app\detector.py"
s = open(p, encoding="utf-8").read()


def rep(a, b):
    global s
    assert a in s, a[:80]
    s = s.replace(a, b, 1)


rep('''            procs = [preprocess(f)[0] for _, f in chunk]
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
                ann = draw(frame, shown, label_track)''', '''            # adaptive sampling: while the road looks clear only every third frame is analysed; as soon as damage
            # shows up every frame is analysed for the next stretch, so tracks and confidence build quickly
            analyse = [k for k in range(len(chunk)) if dense_left > 0 or k % SPARSE_EVERY == 0]
            procs = {k: preprocess(chunk[k][1])[0] for k in analyse}
            dets_l = infer_batch([procs[k] for k in analyse], conf_floor=0.1, imgsz=cfg["imgsz"])
            dets = dict(zip(analyse, dets_l))
            want = [k for k in analyse if (chunk[k][0] // stride) % tile_every == 0] if FAR_PASS else []
            if want:
                far_res = infer_tiles([procs[k] for k in want], imgsz=cfg["imgsz"], mode="far")
                far_by = dict(zip(want, far_res))
            else:
                far_by = {}
            for k, (n, frame) in enumerate(chunk):
                if k in dets:
                    if k in far_by:
                        far_held = far_by[k]
                    d = dets[k]
                    if far_held is not None and len(far_held):
                        d = merge_dets(d, far_held)
                    rows = tk.step(procs[k], time_s=n / fps, dets=d)
                    shown = [r for r in rows if r["confirmed"]]
                    last_shown = shown
                    seen_damage = any(r.get("class_name") == "pothole" and float(r.get("confidence") or 0) >= 0.3 for r in rows)
                    dense_left = DENSE_FRAMES if seen_damage else max(0, dense_left - 1)
                else:
                    shown = last_shown
                    dense_left = max(0, dense_left - 1)
                ann = draw(frame, shown, label_track)''')
rep('''    far_held = None

    def read_chunk():''', '''    far_held = None
    last_shown, dense_left = [], 0

    def read_chunk():''')
rep('VIDEO_BATCH = int(os.getenv("RD_VIDEO_BATCH", "6"))', 'VIDEO_BATCH = int(os.getenv("RD_VIDEO_BATCH", "6"))\nSPARSE_EVERY = int(os.getenv("RD_SPARSE_EVERY", "3"))   # analyse 1 frame in N while nothing is seen\nDENSE_FRAMES = int(os.getenv("RD_DENSE_FRAMES", "24"))   # then analyse every frame for this many frames')
open(p, "w", encoding="utf-8", newline="\n").write(s)
print("ok")

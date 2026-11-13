"""One-off patch: batched inference, magnified tiles for far potholes, precomputed detections in Tracker.step."""
p = r"D:\coding\Hackvalley\backend\app\detector.py"
s = open(p, encoding="utf-8").read()


def rep(a, b):
    global s
    assert a in s, a[:70]
    s = s.replace(a, b, 1)


i = s.index("def infer(img, cracks=None, conf_floor=None, imgsz=None):")
j = s.index("FAR_PASS = os.getenv")
new_infer = '''def _drop_rim_cracks(d):
    """A crack box that mostly overlaps a pothole box is the pothole's broken rim: drop it."""
    if not len(d):
        return d
    pot = d.xyxy[d.cls == CLS_ID["pothole"]]
    keep = np.ones(len(d), bool)
    if len(pot):
        for i in range(len(d)):
            if d.cls[i] != CLS_ID["pothole"] and _iou(d.xyxy[i], pot).max() > 0.5:
                keep[i] = False
    return d[keep]


def infer_batch(frames, cracks=None, conf_floor=None, imgsz=None):
    """Run the ensemble on several BGR frames at once (one batched GPU call per model). Returns one Dets per frame
    with unified class ids (config.CLASSES). Batching is what makes video analysis fast."""
    roles = _load()
    cracks = USE_CRACKS if cracks is None else cracks
    n = len(frames)
    acc = [([], [], []) for _ in range(n)]
    with _infer_lock:
        for r in roles:
            if r.role in ("cracks", "features") and not cracks:
                continue
            c = r.conf if conf_floor is None else min(r.conf, conf_floor)
            results = r.model.predict(list(frames), conf=c, iou=config.IOU_THRESHOLD, imgsz=imgsz or config.IMG_SIZE,
                                      quantize=16, verbose=False, batch=max(1, n))
            for k, res in enumerate(results):
                b = res.boxes
                if b is None or not len(b):
                    continue
                for xy, cf, cl in zip(b.xyxy.cpu().numpy(), b.conf.cpu().numpy(), b.cls.cpu().numpy().astype(int)):
                    name = r.cmap.get(int(cl))
                    if name is None:
                        continue
                    acc[k][0].append(xy)
                    acc[k][1].append(float(cf))
                    acc[k][2].append(CLS_ID[name])
    return [_drop_rim_cracks(Dets(*a)) for a in acc]


def infer(img, cracks=None, conf_floor=None, imgsz=None):
    """Run the ensemble on one BGR frame."""
    return infer_batch([img], cracks=cracks, conf_floor=conf_floor, imgsz=imgsz)[0]


'''
s = s[:i] + new_infer + s[j:]

i = s.index("def infer_far(img, imgsz=None):")
j = s.index("def merge_dets(a: Dets, b: Dets, iou_thr=0.45):")
new_far = '''def _tiles(w, h, mode):
    """Overlapping crops (x1, y1, x2, y2) that magnify small, distant potholes. The old far pass enlarged one wide
    crop and then shrank it back to the detector size, so it gave no extra detail; these tiles are small enough
    that the detector sees them at 1.5 to 3 times the normal scale."""
    tw = 0.42 * w
    xs = [0.0, (w - tw) / 2, w - tw]
    th = 0.42 * w * 0.62
    if mode == "far":      # video: the band between the horizon and the middle of the road
        bands = [(0.27, 0.27 + th / h)]
    else:                  # photo: whole frame, two rows
        bands = [(0.12, 0.12 + th / h), (0.50, 0.50 + th / h)]
    out = []
    for b0, b1 in bands:
        y1, y2 = int(b0 * h), int(min(b1, 0.98) * h)
        if y2 - y1 < 64:
            y1, y2 = int(0.25 * h), int(0.7 * h)
        for x in xs:
            out.append((int(x), y1, int(x + tw), y2))
    return out


def _nms_same(d, thr=0.5):
    order = np.argsort(-d.conf)
    keep = []
    for i in order:
        if all(_iou(d.xyxy[i], d.xyxy[[k]])[0] < thr for k in keep):
            keep.append(int(i))
    return d[np.array(keep, int)]


def infer_tiles(frames, imgsz=None, mode="far"):
    """Pothole-only detections from magnified tiles, mapped back to full-frame coordinates. One batched call."""
    roles = [r for r in _load() if r.role == "pothole"]
    if not roles or not len(frames):
        return [Dets([], [], []) for _ in frames]
    crops, owners = [], []
    for fi, img in enumerate(frames):
        h, w = img.shape[:2]
        for (x1, y1, x2, y2) in _tiles(w, h, mode):
            c = img[y1:y2, x1:x2]
            if c.size:
                crops.append(c)
                owners.append((fi, x1, y1))
    acc = [([], []) for _ in frames]
    if crops:
        with _infer_lock:
            r = roles[0]
            results = r.model.predict(crops, conf=0.2, iou=config.IOU_THRESHOLD, imgsz=imgsz or config.IMG_SIZE,
                                      quantize=16, verbose=False, batch=min(12, max(1, len(crops))))
            for (fi, ox, oy), res in zip(owners, results):
                b = res.boxes
                if b is None or not len(b):
                    continue
                for xy, cf, cl in zip(b.xyxy.cpu().numpy(), b.conf.cpu().numpy(), b.cls.cpu().numpy().astype(int)):
                    if r.cmap.get(int(cl)) != "pothole":
                        continue
                    bx = xy.copy()
                    bx[[0, 2]] += ox
                    bx[[1, 3]] += oy
                    acc[fi][0].append(bx)
                    acc[fi][1].append(float(cf) * 0.95)  # tiny discount: a tile sees less context
    out = []
    for bx, cf in acc:
        d = Dets(bx, cf, [CLS_ID["pothole"]] * len(bx))
        out.append(_nms_same(d) if len(d) else d)
    return out


def infer_far(img, imgsz=None):
    """Single-frame far pass (live camera): horizon band tiles."""
    return infer_tiles([img], imgsz, "far")[0]


'''
s = s[:i] + new_far + s[j:]

rep('''    d = infer_accurate(proc) if ACCURATE_UPLOADS else infer(proc)
    rows = rows_from(img, d)''', '''    d = infer_accurate(proc) if ACCURATE_UPLOADS else infer(proc)
    if FAR_PASS:  # magnified tiles find small, far-away potholes the full-frame pass misses
        far = infer_tiles([proc], mode="photo")[0]
        ok = far.conf >= POTHOLE_CONF if len(far) else None
        if len(far) and ok.any():
            d = merge_dets(d, Dets(far.xyxy[ok], far.conf[ok], far.cls[ok]))
    rows = rows_from(img, d)''')

rep('''    def step(self, frame, cracks=None, time_s=None):
        """Detect + track one frame. Returns list of rows for the currently visible tracks."""
        self.h, self.w = frame.shape[:2]
        proc, _ = preprocess(frame)
        d = infer(proc, cracks=cracks, conf_floor=0.1, imgsz=self.imgsz)
        if FAR_PASS and self.far and self.frame_idx % 2 == 0:
            self._far = infer_far(proc, self.imgsz)
        far = getattr(self, "_far", None)
        if FAR_PASS and self.far and far is not None and len(far):
            d = merge_dets(d, far)''', '''    def step(self, frame, cracks=None, time_s=None, dets=None):
        """Detect + track one frame. Returns list of rows for the currently visible tracks.
        dets: detections already computed (batched video path); otherwise they are computed here."""
        self.h, self.w = frame.shape[:2]
        if dets is not None:
            proc, d = frame, dets
        else:
            proc, _ = preprocess(frame)
            d = infer(proc, cracks=cracks, conf_floor=0.1, imgsz=self.imgsz)
            if FAR_PASS and self.far and self.frame_idx % 2 == 0:
                self._far = infer_far(proc, self.imgsz)
            far = getattr(self, "_far", None)
            if FAR_PASS and self.far and far is not None and len(far):
                d = merge_dets(d, far)''')
open(p, "w", encoding="utf-8", newline="\n").write(s)
print("patched")

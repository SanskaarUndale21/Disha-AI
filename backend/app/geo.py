"""Location helpers: EXIF GPS, GPX track interpolation, haversine distance.

Fallback chain per upload: EXIF GPS -> GPX track -> manual pin -> unknown (NULL, never faked).
"""
import math
import xml.etree.ElementTree as ET
from bisect import bisect_left
from datetime import datetime, timezone

from PIL import Image


def _to_float(v):
    try:
        return float(v)
    except TypeError:
        return float(v[0]) / float(v[1])


def _dms_to_deg(v, ref):
    d = _to_float(v[0]) + _to_float(v[1]) / 60 + _to_float(v[2]) / 3600
    return -d if ref in ("S", "W") else d


def read_exif(path):
    """Return dict(lat, lon, captured_at) from photo EXIF; missing fields are None."""
    out = {"lat": None, "lon": None, "captured_at": None}
    try:
        exif = Image.open(path).getexif()
    except Exception:
        return out
    try:
        gps = exif.get_ifd(0x8825)
        if gps and 2 in gps and 4 in gps:
            lat = _dms_to_deg(gps[2], gps.get(1, "N"))
            lon = _dms_to_deg(gps[4], gps.get(3, "E"))
            if -90 <= lat <= 90 and -180 <= lon <= 180 and not (lat == 0 and lon == 0):
                out["lat"], out["lon"] = lat, lon
    except Exception:
        pass
    try:
        sub = exif.get_ifd(0x8769)
        dt = sub.get(36867) or exif.get(306)
        if dt:
            out["captured_at"] = datetime.strptime(str(dt).strip(), "%Y:%m:%d %H:%M:%S")
    except Exception:
        pass
    return out


def haversine_m(lat1, lon1, lat2, lon2):
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


class GpxTrack:
    """Parsed GPX track; position(t) interpolates lat/lon at seconds offset from video start."""

    def __init__(self, points):
        self.points = sorted(points)  # (epoch_seconds, lat, lon)
        self.times = [p[0] for p in self.points]

    @classmethod
    def parse(cls, data: bytes):
        root = ET.fromstring(data)
        pts = []
        for el in root.iter():
            if el.tag.endswith("trkpt") or el.tag.endswith("wpt") or el.tag.endswith("rtept"):
                lat, lon = el.get("lat"), el.get("lon")
                t = None
                for ch in el:
                    if ch.tag.endswith("time") and ch.text:
                        txt = ch.text.strip().replace("Z", "+00:00")
                        try:
                            t = datetime.fromisoformat(txt)
                            if t.tzinfo is None:
                                t = t.replace(tzinfo=timezone.utc)
                        except ValueError:
                            t = None
                if lat and lon:
                    pts.append((t.timestamp() if t else float(len(pts)), float(lat), float(lon)))
        if not pts:
            raise ValueError("GPX has no track points")
        return cls(pts)

    @property
    def start(self):
        return self.times[0]

    def position(self, seconds_from_start: float, offset_s: float = 0.0):
        t = self.start + seconds_from_start + offset_s
        i = bisect_left(self.times, t)
        if i <= 0:
            return self.points[0][1], self.points[0][2]
        if i >= len(self.points):
            return self.points[-1][1], self.points[-1][2]
        t0, la0, lo0 = self.points[i - 1]
        t1, la1, lo1 = self.points[i]
        f = 0 if t1 == t0 else (t - t0) / (t1 - t0)
        return la0 + (la1 - la0) * f, lo0 + (lo1 - lo0) * f

from pathlib import Path
import os

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
try:  # local secrets (Supabase etc.) live in backend/.env, never in code
    from dotenv import load_dotenv
    load_dotenv(BACKEND / ".env")
except ImportError:
    pass
STORAGE = Path(os.getenv("RD_STORAGE", BACKEND / "storage"))
UPLOADS = STORAGE / "uploads"
ANNOTATED = STORAGE / "annotated"
CROPS = STORAGE / "crops"
REPORTS = STORAGE / "reports"
for p in (UPLOADS, ANNOTATED, CROPS, REPORTS):
    p.mkdir(parents=True, exist_ok=True)

DB_URL = os.getenv("RD_DB_URL") or f"sqlite:///{(STORAGE / 'roadwatch.db').as_posix()}"

# Supabase (auth + Postgres)
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_PUBLISHABLE_KEY", "")
ADMIN_EMAILS = {e.strip().lower() for e in os.getenv("RD_ADMIN_EMAILS", "").split(",") if e.strip()}
OFFICER_EMAILS = {e.strip().lower() for e in os.getenv("RD_OFFICER_EMAILS", "").split(",") if e.strip()}
AUTH_REQUIRED = os.getenv("RD_AUTH_REQUIRED", "1" if SUPABASE_URL else "0") == "1"

# weights: first existing wins (fine-tuned > pretrained baseline)
WEIGHT_CANDIDATES = [
    os.getenv("RD_WEIGHTS", ""),
    str(ROOT / "models" / "best.pt"),
    str(ROOT / "models" / "rdd2022_yolov8m.pt"),
]

CONF_THRESHOLD = float(os.getenv("RD_CONF", "0.25"))
IOU_THRESHOLD = float(os.getenv("RD_IOU", "0.5"))
IMG_SIZE = int(os.getenv("RD_IMGSZ", "640"))

# video
VIDEO_FRAME_STRIDE = int(os.getenv("RD_VIDEO_STRIDE", "1"))
VIDEO_MAX_FRAMES = int(os.getenv("RD_VIDEO_MAX_FRAMES", "3000"))
TRACK_MIN_HITS = int(os.getenv("RD_TRACK_MIN_HITS", "3"))

# duplicate detection
DUP_RADIUS_M = float(os.getenv("RD_DUP_RADIUS_M", "15"))
DUP_RADIUS_MANUAL_M = float(os.getenv("RD_DUP_RADIUS_MANUAL_M", "30"))
DUP_SIM_THRESHOLD = float(os.getenv("RD_DUP_SIM", "0.75"))
DUP_SIM_NO_GPS = float(os.getenv("RD_DUP_SIM_NO_GPS", "0.85"))
REPAIR_RADIUS_M = float(os.getenv("RD_REPAIR_RADIUS_M", "8"))

# citizen app: voice agent helpline (Sarvam RoadWatch agent)
HELPLINE_NUMBER = os.getenv("RD_HELPLINE", "+918064270577")

# canonical class names (RDD2022 D00, D10, D20, D40)
CLASS_ALIASES = {
    "d00": "longitudinal_crack", "longitudinal": "longitudinal_crack", "longitudinal crack": "longitudinal_crack",
    "d10": "transverse_crack", "transverse": "transverse_crack", "transverse crack": "transverse_crack",
    "d20": "alligator_crack", "alligator": "alligator_crack", "alligator crack": "alligator_crack",
    "d40": "pothole", "pothole": "pothole", "potholes": "pothole",
    "manhole": "manhole", "speed_breaker": "speed_breaker", "speedbump": "speed_breaker", "speed bump": "speed_breaker",
    "debris": "debris", "barricade": "barricade", "road_barricade": "barricade", "road barricade": "barricade",
}
CLASSES = ["longitudinal_crack", "transverse_crack", "alligator_crack", "pothole",
           "manhole", "speed_breaker", "debris", "barricade"]
CLASS_LABELS = {
    "longitudinal_crack": "Longitudinal Crack (D00)",
    "transverse_crack": "Transverse Crack (D10)",
    "alligator_crack": "Alligator Crack (D20)",
    "pothole": "Pothole (D40)",
    "manhole": "Manhole / drain cover",
    "speed_breaker": "Speed breaker",
    "debris": "Debris / loose gravel",
    "barricade": "Barricade / work zone",
}


def canonical_class(name: str) -> str:
    n = str(name).strip().lower().replace("-", " ").replace("_", " ")
    return CLASS_ALIASES.get(n, CLASS_ALIASES.get(n.replace(" ", ""), n.replace(" ", "_")))

from datetime import datetime, timezone

from sqlalchemy import (JSON, Boolean, Column, DateTime, Float, ForeignKey, Integer, LargeBinary, String, Text,
                        create_engine)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

from .config import DB_URL

_sqlite = DB_URL.startswith("sqlite")
engine = create_engine(DB_URL, connect_args={"check_same_thread": False} if _sqlite else {},
                       pool_pre_ping=True, pool_size=5 if not _sqlite else 5, pool_recycle=300)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
Base = declarative_base()


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Inspection(Base):
    """One upload (image or video) = one inspection of a road stretch."""
    __tablename__ = "inspections"
    id = Column(Integer, primary_key=True)
    media_type = Column(String(10))  # image | video
    original_name = Column(String(255))
    stored_path = Column(String(512))
    annotated_path = Column(String(512))
    width = Column(Integer)
    height = Column(Integer)
    frames_processed = Column(Integer, default=1)
    fps = Column(Float)
    captured_at = Column(DateTime, default=now)  # inspection date (EXIF or user supplied)
    created_at = Column(DateTime, default=now)
    lat = Column(Float, nullable=True)
    lon = Column(Float, nullable=True)
    location_source = Column(String(20), default="unknown")  # exif | gpx | manual | unknown
    address = Column(String(255))
    road_name = Column(String(255))
    road_type = Column(String(20), default="unknown")  # highway | arterial | collector | local | unknown
    traffic_level = Column(String(20), default="unknown")  # high | medium | low | unknown
    inspector = Column(String(100))
    notes = Column(Text)
    image_hash = Column(String(32))
    duplicate_of_inspection = Column(Integer, nullable=True)
    processing_ms = Column(Integer)
    model_name = Column(String(100))
    summary = Column(JSON)
    detections = relationship("Detection", back_populates="inspection", cascade="all, delete-orphan")


class Defect(Base):
    """A unique physical defect in the world (deduplicated across uploads)."""
    __tablename__ = "defects"
    id = Column(Integer, primary_key=True)
    uid = Column(String(20), unique=True, index=True)
    class_name = Column(String(40))
    lat = Column(Float, nullable=True)
    lon = Column(Float, nullable=True)
    location_source = Column(String(20), default="unknown")
    road_type = Column(String(20), default="unknown")
    traffic_level = Column(String(20), default="unknown")
    severity = Column(String(10))
    severity_score = Column(Float)
    risk_score = Column(Float)
    risk_level = Column(String(10))
    status = Column(String(20), default="active")  # active | repaired | rejected
    trend = Column(String(20), default="new")  # new | worsening | improving | stable | repaired
    report_count = Column(Integer, default=1)
    embedding = Column(LargeBinary, nullable=True)
    best_crop = Column(String(512))
    first_seen = Column(DateTime, default=now)
    last_seen = Column(DateTime, default=now)
    verified = Column(Boolean, default=False)
    detections = relationship("Detection", back_populates="defect")


class Detection(Base):
    __tablename__ = "detections"
    id = Column(Integer, primary_key=True)
    inspection_id = Column(Integer, ForeignKey("inspections.id"), index=True)
    defect_id = Column(Integer, ForeignKey("defects.id"), nullable=True, index=True)
    class_name = Column(String(40))
    confidence = Column(Float)
    x1 = Column(Float)
    y1 = Column(Float)
    x2 = Column(Float)
    y2 = Column(Float)
    area_ratio = Column(Float)
    severity = Column(String(10))
    severity_score = Column(Float)
    risk_score = Column(Float)
    risk_level = Column(String(10))
    track_id = Column(Integer, nullable=True)
    frame_index = Column(Integer, default=0)
    frames_seen = Column(Integer, default=1)
    lat = Column(Float, nullable=True)
    lon = Column(Float, nullable=True)
    crop_path = Column(String(512))
    is_duplicate = Column(Boolean, default=False)
    match_score = Column(Float, nullable=True)
    match_distance_m = Column(Float, nullable=True)
    verification = Column(String(20), default="pending")  # pending | confirmed | rejected | corrected
    corrected_class = Column(String(40), nullable=True)
    corrected_severity = Column(String(10), nullable=True)
    verified_by = Column(String(100), nullable=True)
    verified_at = Column(DateTime, nullable=True)
    verify_note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=now)
    inspection = relationship("Inspection", back_populates="detections")
    defect = relationship("Defect", back_populates="detections")

    @property
    def final_class(self):
        return self.corrected_class or self.class_name

    @property
    def final_severity(self):
        return self.corrected_severity or self.severity


class DefectHistory(Base):
    """Timeline of a defect: one row per inspection that observed (or did not observe) it."""
    __tablename__ = "defect_history"
    id = Column(Integer, primary_key=True)
    defect_id = Column(Integer, ForeignKey("defects.id"), index=True)
    inspection_id = Column(Integer, ForeignKey("inspections.id"))
    observed_at = Column(DateTime)
    present = Column(Boolean, default=True)
    area_ratio = Column(Float, nullable=True)
    severity = Column(String(10), nullable=True)
    severity_score = Column(Float, nullable=True)
    risk_score = Column(Float, nullable=True)
    trend = Column(String(20))


class Complaint(Base):
    """Citizen complaint filed from the mobile app. Each attached media file becomes an Inspection."""
    __tablename__ = "complaints"
    id = Column(Integer, primary_key=True)
    ticket = Column(String(20), unique=True, index=True)
    category = Column(String(40), default="pothole")  # pothole | crack | waterlogging | broken_road | other
    description = Column(Text)
    citizen_name = Column(String(100))
    citizen_phone = Column(String(20), index=True)
    device_id = Column(String(64), index=True)
    citizen_user_id = Column(String(64), index=True, nullable=True)  # Supabase auth user id, None = anonymous
    lat = Column(Float, nullable=True)
    lon = Column(Float, nullable=True)
    address = Column(String(255))
    status = Column(String(20), default="submitted")  # submitted | in_review | in_progress | resolved | rejected
    admin_note = Column(Text)
    created_at = Column(DateTime, default=now)
    updated_at = Column(DateTime, default=now)
    media = relationship("ComplaintMedia", back_populates="complaint", cascade="all, delete-orphan")


class ComplaintMedia(Base):
    __tablename__ = "complaint_media"
    id = Column(Integer, primary_key=True)
    complaint_id = Column(Integer, ForeignKey("complaints.id"), index=True)
    inspection_id = Column(Integer, ForeignKey("inspections.id"), nullable=True)
    job_id = Column(String(40), nullable=True)
    media_type = Column(String(10))
    complaint = relationship("Complaint", back_populates="media")
    inspection = relationship("Inspection")


class Profile(Base):
    """App user. id = Supabase auth user id. role: citizen | officer | admin."""
    __tablename__ = "profiles"
    id = Column(String(64), primary_key=True)
    email = Column(String(255), unique=True, index=True)
    full_name = Column(String(120))
    phone = Column(String(20))
    role = Column(String(20), default="citizen", index=True)
    ward = Column(String(80))  # officer's jurisdiction (ward / zone)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=now)
    last_seen = Column(DateTime, default=now)


def init_db():
    Base.metadata.create_all(engine)
    _add_missing_columns()


def _add_missing_columns():
    """create_all never alters existing tables: add columns introduced later (additive only)."""
    from sqlalchemy import inspect, text
    wanted = {"complaints": {"citizen_user_id": "VARCHAR(64)"}}
    insp = inspect(engine)
    with engine.begin() as conn:
        for table, cols in wanted.items():
            if not insp.has_table(table):
                continue
            have = {c["name"] for c in insp.get_columns(table)}
            for col, ddl in cols.items():
                if col not in have:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}"))
                    conn.execute(text(f"CREATE INDEX IF NOT EXISTS ix_{table}_{col} ON {table} ({col})"))


def get_session():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()

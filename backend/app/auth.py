"""Supabase Auth integration and role-based access (citizen / officer / admin).

Clients sign in with Supabase Auth (email + password, from the web dashboard or the citizen app) and send
`Authorization: Bearer <access_token>`. The backend validates the token with Supabase (`GET /auth/v1/user`,
cached briefly), then loads or creates the user's row in `profiles`, which holds the role.

Roles:
  citizen : default for every new sign-up. Files complaints, sees their own complaints.
  officer : reviews detections, updates defect status, manages complaints (set by an admin).
  admin   : everything officers can do + manage users. Emails in RD_ADMIN_EMAILS become admin on first login.
"""
import time
import threading
from typing import Optional

import httpx
from fastapi import Depends, Header, HTTPException

from . import config
from .db import Profile, SessionLocal, now

_cache: dict = {}
_lock = threading.Lock()
TTL = 120
ROLES = ("citizen", "officer", "admin")
RANK = {"citizen": 0, "officer": 1, "admin": 2}


def _verify(token: str) -> dict:
    hit = _cache.get(token)
    if hit and hit[0] > time.time():
        return hit[1]
    if not config.SUPABASE_URL:
        raise HTTPException(503, "Supabase auth is not configured")
    try:
        r = httpx.get(f"{config.SUPABASE_URL}/auth/v1/user", timeout=8,
                      headers={"apikey": config.SUPABASE_KEY, "Authorization": f"Bearer {token}"})
    except httpx.HTTPError:
        raise HTTPException(503, "Auth service unreachable")
    if r.status_code != 200:
        raise HTTPException(401, "Invalid or expired session, sign in again")
    user = r.json()
    with _lock:
        if len(_cache) > 2000:
            _cache.clear()
        _cache[token] = (time.time() + TTL, user)
    return user


def _profile_for(user: dict) -> dict:
    s = SessionLocal()
    try:
        p = s.get(Profile, user["id"])
        email = (user.get("email") or "").lower()
        meta = user.get("user_metadata") or {}
        if p is None:
            p = Profile(id=user["id"], email=email, full_name=meta.get("full_name") or meta.get("name"),
                        phone=user.get("phone") or meta.get("phone"),
                        role="admin" if email in config.ADMIN_EMAILS
                        else "officer" if email in config.OFFICER_EMAILS else "citizen")
            s.add(p)
        elif email in config.ADMIN_EMAILS and p.role != "admin":
            p.role = "admin"
        elif email in config.OFFICER_EMAILS and p.role == "citizen":
            p.role = "officer"
        p.last_seen = now()
        s.commit()
        return ser_profile(p)
    finally:
        s.close()


def ser_profile(p: Profile) -> dict:
    return {"id": p.id, "email": p.email, "full_name": p.full_name, "phone": p.phone, "role": p.role,
            "ward": p.ward, "active": p.active, "created_at": p.created_at, "last_seen": p.last_seen}


def optional_user(authorization: Optional[str] = Header(None)) -> Optional[dict]:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    prof = _profile_for(_verify(authorization.split(" ", 1)[1].strip()))
    if not prof["active"]:
        raise HTTPException(403, "Account disabled")
    return prof


def current_user(user: Optional[dict] = Depends(optional_user)) -> dict:
    if user is None:
        raise HTTPException(401, "Sign in required")
    return user


def require(role: str):
    """Dependency factory: require at least `role`. When auth is not configured (RD_AUTH_REQUIRED=0) it is open."""

    def dep(user: Optional[dict] = Depends(optional_user)) -> Optional[dict]:
        if not config.AUTH_REQUIRED:
            return user
        if user is None:
            raise HTTPException(401, "Sign in required")
        if RANK.get(user["role"], 0) < RANK[role]:
            raise HTTPException(403, f"{role} access required")
        return user

    return dep


require_officer = require("officer")
require_admin = require("admin")


def register_routes(app):
    from pydantic import BaseModel

    @app.get("/api/auth/config")
    def auth_config():
        """Public: what the frontends need to start Supabase Auth."""
        return {"supabase_url": config.SUPABASE_URL, "supabase_key": config.SUPABASE_KEY,
                "auth_required": config.AUTH_REQUIRED}

    @app.get("/api/me")
    def me(user: dict = Depends(current_user)):
        return user

    class MePatch(BaseModel):
        full_name: Optional[str] = None
        phone: Optional[str] = None

    @app.patch("/api/me")
    def update_me(body: MePatch, user: dict = Depends(current_user)):
        s = SessionLocal()
        try:
            p = s.get(Profile, user["id"])
            for k, v in body.model_dump(exclude_none=True).items():
                setattr(p, k, v)
            s.commit()
            return ser_profile(p)
        finally:
            s.close()

    @app.get("/api/admin/users")
    def list_users(role: Optional[str] = None, _: dict = Depends(require_admin)):
        s = SessionLocal()
        try:
            q = s.query(Profile)
            if role:
                q = q.filter(Profile.role == role)
            return [ser_profile(p) for p in q.order_by(Profile.created_at.desc()).all()]
        finally:
            s.close()

    class UserPatch(BaseModel):
        role: Optional[str] = None
        ward: Optional[str] = None
        active: Optional[bool] = None

    @app.patch("/api/admin/users/{uid}")
    def update_user(uid: str, body: UserPatch, admin: dict = Depends(require_admin)):
        if body.role and body.role not in ROLES:
            raise HTTPException(400, f"role must be one of {ROLES}")
        if uid == (admin or {}).get("id") and body.role and body.role != "admin":
            raise HTTPException(400, "You cannot remove your own admin role")
        s = SessionLocal()
        try:
            p = s.get(Profile, uid)
            if not p:
                raise HTTPException(404, "User has not signed in yet")
            for k, v in body.model_dump(exclude_none=True).items():
                setattr(p, k, v)
            s.commit()
            return ser_profile(p)
        finally:
            s.close()

"""Telegram notifications: a free replacement for SMS that needs no carrier template and no paid account.

How it works
  1. Create a bot in Telegram with @BotFather and copy its token into backend/.env as TELEGRAM_BOT_TOKEN.
  2. A citizen opens the bot once and taps Start, then shares their phone number with the button the bot shows.
     The bot stores phone -> chat id. (Telegram bots cannot message a number that never opened the bot.)
  3. From then on every notification for that phone number, including the 'add a photo within 6 hours' link, goes to
     their Telegram chat. sms.send_sms() tries Telegram first and falls back to the phone gateway or Twilio.
The bot runs on long polling, so no public webhook is needed. Endpoints: GET /api/telegram/status (officer),
POST /api/telegram/test {phone, text} (officer), GET /api/telegram/link (public: the t.me link to start the bot).
"""
import os
import re
import threading
import time
from typing import Optional

import httpx
from fastapi import Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import Column, DateTime, String

from . import auth
from .db import Base, SessionLocal, engine, now

API = "https://api.telegram.org"
_state = {"username": None, "ok": False, "error": None, "offset": 0}


class TelegramLink(Base):
    __tablename__ = "telegram_links"
    phone = Column(String(20), primary_key=True)   # normalised +91XXXXXXXXXX
    chat_id = Column(String(30), index=True)
    name = Column(String(120))
    created_at = Column(DateTime, default=now)


def _token() -> str:
    return os.getenv("TELEGRAM_BOT_TOKEN", "").strip()


def configured() -> bool:
    return bool(_token())


def _norm(phone: str) -> Optional[str]:
    d = re.sub(r"[^\d+]", "", phone or "")
    if d.startswith("+") and 8 <= len(d) <= 16:
        return d
    d = d.lstrip("0")
    if len(d) == 10:
        return "+91" + d
    if len(d) >= 11 and d.startswith("91"):
        return "+" + d
    return None


def _call(method: str, **params):
    r = httpx.post(f"{API}/bot{_token()}/{method}", json=params, timeout=35)
    j = r.json()
    if not j.get("ok"):
        raise RuntimeError(j.get("description", f"telegram error {r.status_code}"))
    return j["result"]


def send_to_chat(chat_id, text: str) -> dict:
    try:
        _call("sendMessage", chat_id=chat_id, text=text[:3500], disable_web_page_preview=False)
        return {"ok": True, "provider": "telegram"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:150], "provider": "telegram"}


def chat_for_phone(phone: str) -> Optional[str]:
    p = _norm(phone)
    if not p:
        return None
    s = SessionLocal()
    try:
        row = s.get(TelegramLink, p)
        return row.chat_id if row else None
    finally:
        s.close()


def send_to_phone(phone: str, text: str) -> dict:
    """Send to the Telegram chat linked to this phone number, if any."""
    if not configured():
        return {"ok": False, "error": "Telegram bot is not configured", "provider": "telegram"}
    chat = chat_for_phone(phone)
    if not chat:
        return {"ok": False, "error": "this number has not linked Telegram yet (open the bot and share the contact)", "provider": "telegram"}
    return send_to_chat(chat, text)


def _handle(update: dict):
    m = update.get("message") or {}
    chat = (m.get("chat") or {}).get("id")
    if not chat:
        return
    contact = m.get("contact")
    text = (m.get("text") or "").strip()
    if contact and contact.get("phone_number"):
        # accept only the sender's own contact
        if contact.get("user_id") not in (None, (m.get("from") or {}).get("id")):
            send_to_chat(chat, "Please share your own contact using the button.")
            return
        phone = _norm(contact["phone_number"])
        if not phone:
            send_to_chat(chat, "That phone number could not be read. Please try again.")
            return
        s = SessionLocal()
        try:
            name = " ".join(x for x in (contact.get("first_name"), contact.get("last_name")) if x)[:120]
            row = s.get(TelegramLink, phone) or TelegramLink(phone=phone)
            row.chat_id, row.name = str(chat), name
            s.add(row)
            s.commit()
        finally:
            s.close()
        _call("sendMessage", chat_id=chat, text=f"Linked. Disha AI will message you here about your road complaints ({phone}).",
              reply_markup={"remove_keyboard": True})
    elif text.startswith("/start") or text.lower() in ("hi", "hello", "link"):
        _call("sendMessage", chat_id=chat,
              text="Welcome to Disha AI. Tap the button below to share your phone number, so we can send you the photo upload link and updates "
                   "about your road complaints.",
              reply_markup={"keyboard": [[{"text": "Share my phone number", "request_contact": True}]], "resize_keyboard": True, "one_time_keyboard": True})
    elif text:
        send_to_chat(chat, "Send /start to link your phone number. Your complaint updates will arrive here.")


def _poll_loop():
    while True:
        try:
            if not configured():
                time.sleep(20)
                continue
            if not _state["username"]:
                me = _call("getMe")
                _state["username"], _state["ok"], _state["error"] = me.get("username"), True, None
                try:
                    _call("deleteWebhook")
                except Exception:
                    pass
            r = httpx.post(f"{API}/bot{_token()}/getUpdates", json={"offset": _state["offset"], "timeout": 25, "allowed_updates": ["message"]}, timeout=40)
            for u in r.json().get("result", []):
                _state["offset"] = u["update_id"] + 1
                try:
                    _handle(u)
                except Exception as e:
                    print("[telegram] handler error:", repr(e))
        except Exception as e:
            _state["ok"], _state["error"] = False, str(e)[:120]
            time.sleep(8)


class TestBody(BaseModel):
    phone: str
    text: str = "Disha AI test message."


def register(app):
    Base.metadata.create_all(engine, tables=[TelegramLink.__table__])
    threading.Thread(target=_poll_loop, daemon=True, name="telegram-poll").start()

    @app.get("/api/telegram/link")
    def tg_link():
        if not _state["username"]:
            raise HTTPException(503, "Telegram is not set up yet")
        return {"bot": _state["username"], "url": f"https://t.me/{_state['username']}?start=link"}

    @app.get("/api/telegram/status", dependencies=[Depends(auth.require_officer)])
    def tg_status():
        s = SessionLocal()
        try:
            n = s.query(TelegramLink).count()
        finally:
            s.close()
        return {"configured": configured(), "bot": _state["username"], "ok": _state["ok"], "error": _state["error"], "linked_numbers": n}

    @app.post("/api/telegram/test", dependencies=[Depends(auth.require_officer)])
    def tg_test(b: TestBody):
        r = send_to_phone(b.phone, b.text)
        if not r["ok"]:
            raise HTTPException(400, r["error"])
        return r

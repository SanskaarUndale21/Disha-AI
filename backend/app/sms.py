"""SMS through Twilio. Reads TWILIO_* from backend/.env. Sends nothing until TWILIO_FROM (a Twilio number or sender id) is set.
Trial accounts can only text numbers verified in the Twilio console, so failures are logged and never break the request.

  send_sms(to, body) -> {"ok": bool, "sid"/"error": ...}
  GET  /api/sms/status                (officer) is SMS configured, and the account type
  POST /api/sms/test {to, body}       (officer) sends one message on request only
Complaint status changes text the citizen through notify_status() when a phone number is on file."""
import os
import re
import threading
from typing import Optional

import httpx
from fastapi import Depends, HTTPException
from pydantic import BaseModel

from . import auth


def _cfg():
    sid = os.getenv("TWILIO_ACCOUNT_SID", "")
    key, secret = os.getenv("TWILIO_API_KEY_SID", ""), os.getenv("TWILIO_API_KEY_SECRET", "")
    token = os.getenv("TWILIO_AUTH_TOKEN", "")
    user, pw = (key, secret) if key and secret else (sid, token)
    return {"sid": sid, "auth": (user, pw), "from": os.getenv("TWILIO_FROM", "").strip()}


def configured() -> bool:
    c = _cfg()
    return bool(c["sid"] and c["auth"][0] and c["auth"][1] and c["from"])


def normalize(phone: str, default_cc: str = "+91") -> Optional[str]:
    d = re.sub(r"[^\d+]", "", phone or "")
    if d.startswith("+") and 8 <= len(d) <= 16:
        return d
    d = d.lstrip("0")
    if len(d) == 10:
        return default_cc + d
    if len(d) == 12 and d.startswith("91"):
        return "+" + d
    return None


def send_sms(to: str, body: str) -> dict:
    c = _cfg()
    num = normalize(to)
    if not num:
        return {"ok": False, "error": "invalid phone number"}
    if not configured():
        return {"ok": False, "error": "SMS is not configured (set TWILIO_FROM in backend/.env)"}
    try:
        r = httpx.post(f"https://api.twilio.com/2010-04-01/Accounts/{c['sid']}/Messages.json", auth=c["auth"], timeout=20,
                       data={"To": num, "From": c["from"], "Body": body[:600]})
        j = r.json()
        if r.status_code >= 400:
            return {"ok": False, "error": j.get("message", r.text[:150]), "code": j.get("code")}
        return {"ok": True, "sid": j.get("sid"), "status": j.get("status")}
    except Exception as e:  # network trouble must not break the caller
        return {"ok": False, "error": str(e)[:150]}


STATUS_TEXT = {
    "in_review": "is being reviewed by the roads team",
    "in_progress": "is now being repaired",
    "resolved": "has been repaired. Thank you for reporting",
    "rejected": "was checked and closed without work",
}


def notify_status(phone: Optional[str], ticket: str, status: str):
    """Fire and forget: text the citizen when their complaint changes status."""
    if not phone or status not in STATUS_TEXT or not configured():
        return
    body = f"Disha AI: your complaint {ticket} {STATUS_TEXT[status]}."
    threading.Thread(target=lambda: print("[sms]", ticket, status, send_sms(phone, body)), daemon=True).start()


class TestBody(BaseModel):
    to: str
    body: str = "Disha AI test message."


def register(app):
    @app.get("/api/sms/status", dependencies=[Depends(auth.require_officer)])
    def sms_status():
        c = _cfg()
        acct = None
        try:
            r = httpx.get(f"https://api.twilio.com/2010-04-01/Accounts/{c['sid']}.json", auth=c["auth"], timeout=15)
            acct = r.json().get("type") if r.status_code == 200 else f"error {r.status_code}"
        except Exception:
            acct = "unreachable"
        return {"configured": configured(), "has_credentials": bool(c["sid"] and c["auth"][1]), "from_set": bool(c["from"]), "account": acct}

    @app.post("/api/sms/test", dependencies=[Depends(auth.require_officer)])
    def sms_test(b: TestBody):
        r = send_sms(b.to, b.body)
        if not r["ok"]:
            raise HTTPException(400, r["error"])
        return r

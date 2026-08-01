"""Alerts: unknown-face + blocked-watchlist events, delivered via Resend email and
stored in Mongo so the frontend can poll for browser notifications.
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

import resend

logger = logging.getLogger(__name__)

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "").strip()
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "onboarding@resend.dev")

if RESEND_API_KEY:
    resend.api_key = RESEND_API_KEY


async def send_email(to_email: str, subject: str, html: str) -> Optional[str]:
    if not RESEND_API_KEY or not to_email:
        logger.info("Skipping email (no API key or recipient).")
        return None
    try:
        params = {"from": SENDER_EMAIL, "to": [to_email], "subject": subject, "html": html}
        res = await asyncio.to_thread(resend.Emails.send, params)
        return (res or {}).get("id")
    except Exception as e:  # noqa
        logger.warning("Resend send failed: %s", e)
        return None


def _unknown_email(camera_id: str, similarity: float, image_url: str, base_url: str) -> str:
    full = f"{base_url}{image_url}" if image_url and image_url.startswith("/") else image_url
    return f"""
    <table cellpadding="0" cellspacing="0" border="0" width="100%" style="font-family: -apple-system, Segoe UI, sans-serif; background: #0A0A0A; color: #fff; padding: 32px;">
      <tr><td>
        <table cellpadding="0" cellspacing="0" border="0" width="520" style="margin:0 auto; background:#121212; border:1px solid rgba(255,255,255,0.1); border-radius:8px;">
          <tr><td style="padding: 24px;">
            <div style="color:#FF3B30; font-size:11px; letter-spacing:0.25em; text-transform:uppercase; font-family: monospace;">Unknown person detected</div>
            <h1 style="font-size:24px; margin: 8px 0 4px; color:#fff;">Sentinel FR alert</h1>
            <p style="color:#A1A1AA; font-size:13px; margin:0;">Camera <b style="color:#fff;">{camera_id}</b> captured an unrecognised face.</p>
            <table cellpadding="0" cellspacing="0" style="margin-top:20px; font-family: monospace; font-size:12px; color:#A1A1AA;">
              <tr><td style="padding:4px 12px 4px 0;">Best similarity</td><td style="color:#fff;">{similarity*100:.1f}%</td></tr>
              <tr><td style="padding:4px 12px 4px 0;">Captured at</td><td style="color:#fff;">{datetime.now(timezone.utc).isoformat()}</td></tr>
            </table>
            {"<img src='" + full + "' style='margin-top:20px; width:100%; border-radius:6px; border:1px solid rgba(255,255,255,0.1);'/>" if full else ""}
            <p style="color:#71717A; font-size:11px; margin-top:24px; font-family: monospace;">Review in the Unknown Faces panel.</p>
          </td></tr>
        </table>
      </td></tr>
    </table>
    """


def _blocked_email(name: str, camera_id: str, similarity: float) -> str:
    return f"""
    <div style="font-family:-apple-system, Segoe UI, sans-serif; background:#0A0A0A; color:#fff; padding:32px;">
      <div style="max-width:520px; margin:0 auto; background:#121212; border:1px solid #FF3B30; border-radius:8px; padding:24px;">
        <div style="color:#FF3B30; font-size:11px; letter-spacing:0.25em; text-transform:uppercase;">Blocked identity detected</div>
        <h1 style="margin:8px 0 4px;">{name}</h1>
        <p style="color:#A1A1AA; font-size:13px;">Camera <b>{camera_id}</b> · similarity {similarity*100:.1f}%</p>
      </div>
    </div>
    """


def _vip_email(name: str, camera_id: str) -> str:
    return f"""
    <div style="font-family:-apple-system, Segoe UI, sans-serif; background:#0A0A0A; color:#fff; padding:32px;">
      <div style="max-width:520px; margin:0 auto; background:#121212; border:1px solid #FFD400; border-radius:8px; padding:24px;">
        <div style="color:#FFD400; font-size:11px; letter-spacing:0.25em; text-transform:uppercase;">VIP arrival</div>
        <h1 style="margin:8px 0 4px;">{name}</h1>
        <p style="color:#A1A1AA; font-size:13px;">Camera <b>{camera_id}</b> welcomed a VIP guest.</p>
      </div>
    </div>
    """


async def create_alert(db, kind: str, message: str, camera_id: str, image_url: str = None,
                       user_id: str = None, similarity: float = 0.0, extra: dict = None,
                       recipient: str = None, base_url: str = ""):
    """Store alert record and best-effort send an email."""
    doc = {
        "id": str(uuid.uuid4()),
        "kind": kind,               # "unknown" | "blocked" | "vip"
        "message": message,
        "camera_id": camera_id,
        "user_id": user_id,
        "image_url": image_url,
        "similarity": similarity,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "read": False,
        "extra": extra or {},
    }
    await db.alerts.insert_one(doc)
    doc.pop("_id", None)

    if recipient:
        if kind == "unknown":
            html = _unknown_email(camera_id, similarity, image_url or "", base_url)
            subject = f"[Sentinel FR] Unknown person on {camera_id}"
        elif kind == "blocked":
            html = _blocked_email(extra.get("name") if extra else "Unknown", camera_id, similarity)
            subject = f"[Sentinel FR] BLOCKED identity on {camera_id}"
        elif kind == "vip":
            html = _vip_email(extra.get("name") if extra else "VIP", camera_id)
            subject = f"[Sentinel FR] VIP arrival on {camera_id}"
        else:
            html = f"<p>{message}</p>"
            subject = f"[Sentinel FR] {kind}"
        email_id = await send_email(recipient, subject, html)
        if email_id:
            await db.alerts.update_one({"id": doc["id"]}, {"$set": {"email_id": email_id}})
    return doc


async def get_alert_recipient(db) -> str:
    """Look up the configured recipient from `settings` collection, falling back to env."""
    s = await db.settings.find_one({"_id": "notifications"})
    if s and s.get("alert_email"):
        return s["alert_email"]
    return os.environ.get("ALERT_TO", "").strip() or ""


async def send_sms_notification(phone_number: str, message_text: str) -> bool:
    """Send mobile SMS notification via Twilio if TWILIO_ACCOUNT_SID/AUTH_TOKEN are set."""
    account_sid = os.environ.get("TWILIO_ACCOUNT_SID", "").strip()
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN", "").strip()
    from_phone = os.environ.get("TWILIO_PHONE_NUMBER", "").strip()

    if account_sid and auth_token and from_phone and phone_number:
        try:
            import base64
            import urllib.parse
            import urllib.request
            url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
            data = urllib.parse.urlencode({"To": phone_number, "From": from_phone, "Body": message_text}).encode("utf-8")
            req = urllib.request.Request(url, data=data, method="POST")
            auth_str = f"{account_sid}:{auth_token}"
            b64_auth = base64.b64encode(auth_str.encode("utf-8")).decode("utf-8")
            req.add_header("Authorization", f"Basic {b64_auth}")
            req.add_header("Content-Type", "application/x-www-form-urlencoded")

            def _send():
                with urllib.request.urlopen(req) as resp:
                    return resp.status in (200, 201)

            ok = await asyncio.to_thread(_send)
            logger.info("Sent mobile SMS notification to %s: %s", phone_number, ok)
            return ok
        except Exception as err:
            logger.warning("Mobile SMS notification failed for %s: %s", phone_number, err)
            return False
    return False


async def notify_user_match(db, user_data: dict, camera_id: str, similarity: float):
    """Notify the recognized user directly on mobile via SMS and Email when their face matches."""
    if not user_data:
        return
    name = user_data.get("name", "User")
    phone = user_data.get("phone", "").strip()
    email = user_data.get("email", "").strip()
    watchlist_status = user_data.get("watchlist_status", "normal")
    sim_percent = f"{similarity * 100:.1f}%"

    sms_msg = f"Sentinel FR Alert: Hello {name}, your face match was verified on camera '{camera_id}' ({sim_percent} confidence)."
    if watchlist_status == "vip":
        sms_msg = f"Sentinel FR Alert: Welcome VIP Guest {name}! Face verified on camera '{camera_id}' ({sim_percent} confidence)."

    if phone:
        await send_sms_notification(phone, sms_msg)

    if email:
        subject = f"[Sentinel FR Alert] Face Match Verified: {name}"
        html = f"""
        <div style="font-family: -apple-system, sans-serif; background: #0A0A0A; color: #fff; padding: 24px;">
          <div style="max-width: 480px; margin: 0 auto; background: #121212; border: 1px solid #00FF66; border-radius: 8px; padding: 20px;">
            <div style="color: #00FF66; font-size: 11px; text-transform: uppercase; font-family: monospace;">Face Match Verified</div>
            <h2 style="margin: 8px 0 4px; color: #fff;">Hello {name}</h2>
            <p style="color: #A1A1AA; font-size: 13px;">Your facial identity was recognized on camera <b>{camera_id}</b>.</p>
            <div style="margin-top: 16px; font-family: monospace; font-size: 12px; color: #00FF66;">
              Match Confidence: <b>{sim_percent}</b>
            </div>
          </div>
        </div>
        """
        await send_email(email, subject, html)


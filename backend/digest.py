"""Weekly digest generator — summarises last 7 days of visitor + VIP + unknown data
and sends a rich HTML email via Resend on Monday mornings.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List

from alerts import send_email

logger = logging.getLogger(__name__)


async def compose_digest(db, base_url: str = "") -> Dict:
    now = datetime.now(timezone.utc)
    week_ago = (now - timedelta(days=7)).isoformat()

    # Aggregations
    total_visits = await db.visits.count_documents({"entry_time": {"$gte": week_ago}})
    total_unknown = await db.unknown_people.count_documents({"timestamp": {"$gte": week_ago}})
    unique_visitors = await db.visits.distinct("user_id", {"entry_time": {"$gte": week_ago}})
    unique_count = len(unique_visitors)

    # VIP visits
    vip_users = await db.users.find({"watchlist_status": "vip"}, {"_id": 0}).to_list(500)
    vip_ids = [u["id"] for u in vip_users]
    vip_visits = await db.visits.count_documents({"user_id": {"$in": vip_ids}, "entry_time": {"$gte": week_ago}}) if vip_ids else 0

    # Top spenders (lifetime)
    top_spenders = await db.users.find({}, {"_id": 0}).sort("lifetime_spend", -1).limit(5).to_list(5)
    top_spenders = [t for t in top_spenders if (t.get("lifetime_spend") or 0) > 0]

    # Most frequent visitors this week
    pipeline = [
        {"$match": {"entry_time": {"$gte": week_ago}, "user_id": {"$ne": None}}},
        {"$group": {"_id": "$user_id", "visits": {"$sum": 1}}},
        {"$sort": {"visits": -1}},
        {"$limit": 5},
    ]
    frequent = await db.visits.aggregate(pipeline).to_list(5)
    frequent_ids = [row["_id"] for row in frequent]
    umap = {}
    if frequent_ids:
        u = await db.users.find({"id": {"$in": frequent_ids}}, {"_id": 0}).to_list(len(frequent_ids))
        umap = {x["id"]: x for x in u}
    frequent_visitors = [
        {"name": umap.get(row["_id"], {}).get("name", "Unknown"), "visits": row["visits"]}
        for row in frequent
    ]

    return {
        "period_start": (now - timedelta(days=7)).strftime("%b %d"),
        "period_end": now.strftime("%b %d, %Y"),
        "total_visits": total_visits,
        "unique_visitors": unique_count,
        "vip_visits": vip_visits,
        "total_unknown": total_unknown,
        "top_spenders": top_spenders,
        "frequent_visitors": frequent_visitors,
    }


def _fmt_money(n) -> str:
    try:
        return f"₹{float(n or 0):,.0f}"
    except Exception:
        return "₹0"


def render_digest_html(d: Dict) -> str:
    ts = "".join(
        f"<tr><td style='padding:8px 0;color:#fff'>{i+1}. {v['name']}</td>"
        f"<td style='padding:8px 0;color:#00FF66;text-align:right'>{_fmt_money(v.get('lifetime_spend',0))}</td></tr>"
        for i, v in enumerate(d["top_spenders"])
    ) or "<tr><td colspan=2 style='padding:8px 0;color:#71717A'>No spend data yet.</td></tr>"

    fs = "".join(
        f"<tr><td style='padding:8px 0;color:#fff'>{i+1}. {v['name']}</td>"
        f"<td style='padding:8px 0;color:#fff;text-align:right'>{v['visits']} visits</td></tr>"
        for i, v in enumerate(d["frequent_visitors"])
    ) or "<tr><td colspan=2 style='padding:8px 0;color:#71717A'>No visits this week.</td></tr>"

    return f"""
    <div style="font-family:-apple-system,Segoe UI,sans-serif;background:#0A0A0A;color:#fff;padding:32px;">
      <div style="max-width:600px;margin:0 auto;">
        <div style="color:#00FF66;font-size:11px;letter-spacing:0.3em;text-transform:uppercase;font-family:monospace;margin-bottom:8px;">
          Weekly Digest · {d['period_start']} – {d['period_end']}
        </div>
        <h1 style="margin:0 0 24px;font-size:28px;letter-spacing:-0.01em;">Your store, last 7 days.</h1>

        <table cellpadding="0" cellspacing="0" style="width:100%;border-collapse:separate;border-spacing:8px;margin-bottom:24px;">
          <tr>
            <td style="background:#121212;border:1px solid rgba(255,255,255,0.1);border-radius:6px;padding:16px;width:33%;">
              <div style="font-size:10px;letter-spacing:0.25em;text-transform:uppercase;color:#A1A1AA;font-family:monospace;">Total visits</div>
              <div style="font-size:28px;color:#fff;font-family:monospace;margin-top:6px;">{d['total_visits']}</div>
            </td>
            <td style="background:#121212;border:1px solid rgba(255,255,255,0.1);border-radius:6px;padding:16px;width:33%;">
              <div style="font-size:10px;letter-spacing:0.25em;text-transform:uppercase;color:#A1A1AA;font-family:monospace;">Unique customers</div>
              <div style="font-size:28px;color:#00FF66;font-family:monospace;margin-top:6px;">{d['unique_visitors']}</div>
            </td>
            <td style="background:#121212;border:1px solid rgba(255,255,255,0.1);border-radius:6px;padding:16px;width:33%;">
              <div style="font-size:10px;letter-spacing:0.25em;text-transform:uppercase;color:#A1A1AA;font-family:monospace;">VIP visits</div>
              <div style="font-size:28px;color:#FFD400;font-family:monospace;margin-top:6px;">{d['vip_visits']}</div>
            </td>
          </tr>
        </table>

        <div style="background:#121212;border:1px solid rgba(255,255,255,0.1);border-radius:6px;padding:20px;margin-bottom:20px;">
          <div style="font-size:11px;letter-spacing:0.25em;text-transform:uppercase;color:#A1A1AA;font-family:monospace;margin-bottom:12px;">Top spenders (lifetime)</div>
          <table cellpadding="0" cellspacing="0" style="width:100%;font-family:monospace;font-size:13px;">
            {ts}
          </table>
        </div>

        <div style="background:#121212;border:1px solid rgba(255,255,255,0.1);border-radius:6px;padding:20px;margin-bottom:20px;">
          <div style="font-size:11px;letter-spacing:0.25em;text-transform:uppercase;color:#A1A1AA;font-family:monospace;margin-bottom:12px;">Most frequent visitors this week</div>
          <table cellpadding="0" cellspacing="0" style="width:100%;font-family:monospace;font-size:13px;">
            {fs}
          </table>
        </div>

        {"<div style='background:#FF3B30;border-radius:6px;padding:16px;color:#000;font-family:monospace;font-size:13px;'>⚠ " + str(d['total_unknown']) + " unknown faces are waiting to be reviewed.</div>" if d['total_unknown'] > 0 else ""}

        <div style="color:#71717A;font-size:11px;font-family:monospace;margin-top:32px;">
          Sentinel FR · Retail Intelligence
        </div>
      </div>
    </div>
    """


async def maybe_send_digest(db):
    """Called by the scheduler loop. Sends Monday morning if we haven't yet this week."""
    now = datetime.now(timezone.utc)
    # Monday = 0
    if now.weekday() != 0 or now.hour < 9:
        return False
    settings = await db.settings.find_one({"_id": "notifications"})
    last = (settings or {}).get("last_digest_at")
    if last:
        try:
            last_dt = datetime.fromisoformat(last)
            if (now - last_dt).total_seconds() < 60 * 60 * 24 * 6:
                return False
        except Exception:
            pass
    recipient = (settings or {}).get("alert_email") or ""
    if not recipient:
        logger.info("Skipping weekly digest: no alert_email configured.")
        return False
    data = await compose_digest(db)
    html = render_digest_html(data)
    email_id = await send_email(recipient, f"Sentinel FR Weekly Digest ({data['period_start']} – {data['period_end']})", html)
    await db.settings.update_one(
        {"_id": "notifications"},
        {"$set": {"last_digest_at": now.isoformat(), "last_digest_email_id": email_id}},
        upsert=True,
    )
    logger.info("Weekly digest sent (email_id=%s)", email_id)
    return True


async def scheduler_loop(db):
    """Runs forever in the background — checks once per hour."""
    while True:
        try:
            await maybe_send_digest(db)
        except Exception as e:  # noqa
            logger.warning("digest loop error: %s", e)
        await asyncio.sleep(3600)

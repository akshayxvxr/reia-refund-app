"""
scheduler.py — Background email reminder scheduler.

- No circular import from app.py
- Sleeps in 30s chunks so interval changes apply quickly
- Email matches RÉIA brand: DM Serif Display + DM Sans, exact brand colours
- Sends via Gmail REST API using OAuth2 refresh token (works on Render free tier)
"""

import threading
import time
import os
import json
import base64
from datetime import date, datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

from settings import load_settings
from google_sheets import GoogleSheetsSync

DATA_FILE = "data/refunds.json"
LOGO_URL  = "https://reia-refund-app.onrender.com/static/reia_logo.png"

# Exact brand tokens from base.html
BRAND      = "#1A1A18"
GOLD       = "#BFA27A"
GOLD_LIGHT = "#D4BA94"
GOLD_PALE  = "#EDE0CC"
CREAM      = "#F8F4EE"
CREAM_DARK = "#EDE8DF"
BG         = "#F5F1EB"
MUTED      = "#8A8A80"
HINT       = "#B0AEA6"
BORDER     = "#DDD8CE"
TEXT_SEC   = "#4A4A44"
RED        = "#C0392B"
AMBER      = "#8B6914"
AMBER_BG   = "#FBF4E3"
GREEN      = "#2D6A4F"


# ── Standalone helpers ────────────────────────────────────────────────────────

def _load_local():
    if not os.path.exists(DATA_FILE):
        return []
    try:
        with open(DATA_FILE) as f:
            return json.load(f)
    except Exception:
        return []


def _load_records():
    gs = GoogleSheetsSync()
    if gs.is_configured():
        try:
            return gs.load_all_records()
        except Exception as e:
            print(f"[Scheduler] Sheets load error: {e} — using local")
    return _load_local()


def _compute_days(record) -> int:
    """Always recompute from date field so days_out is never stale."""
    if str(record.get("status", "")).strip().lower() == "completed":
        return 0
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            d = datetime.strptime(str(record.get("date", "")), fmt).date()
            return (date.today() - d).days
        except Exception:
            continue
    return record.get("days_out", 0)


def _get_gmail_service():
    client_id     = os.getenv("OAUTH_CLIENT_ID")
    client_secret = os.getenv("OAUTH_CLIENT_SECRET")
    refresh_token = os.getenv("OAUTH_REFRESH_TOKEN")

    if not all([client_id, client_secret, refresh_token]):
        raise ValueError("OAUTH_CLIENT_ID, OAUTH_CLIENT_SECRET or OAUTH_REFRESH_TOKEN not set")

    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=["https://www.googleapis.com/auth/gmail.send"],
    )
    creds.refresh(Request())
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


# ── Email ─────────────────────────────────────────────────────────────────────

def send_reminder_email(pending_records: list, recipient: str, interval: int):
    sender = os.getenv("GMAIL_USER", "").strip()
    if not sender:
        print("[Scheduler] GMAIL_USER not set — skipping.")
        return

    # Always recompute fresh days
    for r in pending_records:
        r["days_out"] = _compute_days(r)

    total   = sum(r.get("net", 0) for r in pending_records)
    now_str = datetime.now().strftime("%d %b %Y, %I:%M %p")

    rows_html = ""
    for i, r in enumerate(pending_records):
        days = r.get("days_out", 0)
        if days >= 7:
            days_color = RED
            days_label = f"{days} days"
        elif days >= 3:
            days_color = AMBER
            days_label = f"{days} days"
        else:
            days_color = GREEN
            days_label = f"{days} day{'s' if days != 1 else ''}"

        row_bg = "#FFFFFF" if i % 2 == 0 else "#FDFAF6"

        rows_html += f"""
        <tr style="background:{row_bg};">
          <td style="padding:9px 12px;border-bottom:1px solid {CREAM_DARK};font-size:11px;color:{HINT};font-family:'DM Sans',Arial,sans-serif;width:30px;">{r.get('no','')}</td>
          <td style="padding:9px 12px;border-bottom:1px solid {CREAM_DARK};">
            <div style="font-size:12px;color:{BRAND};font-weight:500;font-family:'DM Sans',Arial,sans-serif;">{r.get('name','')}</div>
            <div style="font-size:10px;color:{MUTED};margin-top:1px;font-family:'DM Sans',Arial,sans-serif;">{r.get('store','')}</div>
          </td>
          <td style="padding:9px 12px;border-bottom:1px solid {CREAM_DARK};font-size:12px;color:{BRAND};font-weight:600;font-family:'DM Sans',Arial,sans-serif;white-space:nowrap;">&#8377;{r.get('net',0):,.0f}</td>
          <td style="padding:9px 12px;border-bottom:1px solid {CREAM_DARK};white-space:nowrap;">
            <span style="font-size:11px;font-weight:600;color:{days_color};font-family:'DM Sans',Arial,sans-serif;">{days_label}</span>
          </td>
        </tr>"""

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1.0">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=DM+Sans:opsz,wght@9..40,300;9..40,400;9..40,500;9..40,600&family=DM+Serif+Display&display=swap" rel="stylesheet">
</head>
<body style="margin:0;padding:0;background:{BG};font-family:'DM Sans',Arial,Helvetica,sans-serif;">

  <table width="100%" cellpadding="0" cellspacing="0" style="background:{BG};padding:40px 16px;">
    <tr><td align="center">
      <table width="580" cellpadding="0" cellspacing="0" style="max-width:580px;width:100%;">

        <!-- ── Logo header ── -->
        <tr>
          <td style="background:{BRAND};border-radius:8px 8px 0 0;padding:28px 40px 24px;text-align:center;">
            <img src="{LOGO_URL}" alt="RÉIA"
                 height="34"
                 style="height:34px;display:inline-block;filter:grayscale(1) brightness(10) contrast(1.2);">
            <div style="margin-top:18px;height:1px;background:{BRAND};"></div>
            <p style="margin:12px 0 0;font-size:9px;letter-spacing:0.28em;text-transform:uppercase;color:{GOLD};font-family:'DM Sans',Arial,sans-serif;font-weight:500;">Accounts Portal &nbsp;·&nbsp; Refund Reminder</p>
          </td>
        </tr>

        <!-- ── Table ── -->
        <tr>
          <td style="background:#FFFFFF;padding:0;">
            <table width="100%" cellpadding="0" cellspacing="0">
              <!-- Column headers -->
              <tr style="background:{CREAM};">
                <th style="padding:7px 12px;text-align:left;font-size:9px;font-weight:600;letter-spacing:0.16em;text-transform:uppercase;color:{HINT};font-family:'DM Sans',Arial,sans-serif;border-bottom:1px solid {CREAM_DARK};">#</th>
                <th style="padding:7px 12px;text-align:left;font-size:9px;font-weight:600;letter-spacing:0.16em;text-transform:uppercase;color:{HINT};font-family:'DM Sans',Arial,sans-serif;border-bottom:1px solid {CREAM_DARK};">Customer</th>
                <th style="padding:7px 12px;text-align:left;font-size:9px;font-weight:600;letter-spacing:0.16em;text-transform:uppercase;color:{HINT};font-family:'DM Sans',Arial,sans-serif;border-bottom:1px solid {CREAM_DARK};">Net Refund</th>
                <th style="padding:7px 12px;text-align:left;font-size:9px;font-weight:600;letter-spacing:0.16em;text-transform:uppercase;color:{HINT};font-family:'DM Sans',Arial,sans-serif;border-bottom:1px solid {CREAM_DARK};">Days</th>
              </tr>
              {rows_html}
            </table>
          </td>
        </tr>

        <!-- ── Gold accent bar ── -->
        <tr>
          <td style="background:#FFFFFF;padding:0 40px;">
            <div style="height:2px;background:linear-gradient(90deg,{GOLD} 0%,{GOLD_PALE} 100%);border-radius:1px;"></div>
          </td>
        </tr>

        <!-- ── Footer ── -->
        <tr>
          <td style="background:{CREAM};border-radius:0 0 8px 8px;padding:16px 40px;border-top:1px solid {CREAM_DARK};">
            <table width="100%" cellpadding="0" cellspacing="0">
              <tr>
                <td>
                  <p style="margin:0;font-size:10px;color:{HINT};font-family:'DM Sans',Arial,sans-serif;">Generated {now_str}</p>
                  <p style="margin:3px 0 0;font-size:10px;color:{HINT};font-family:'DM Sans',Arial,sans-serif;">Reminder every {interval} minute(s)</p>
                </td>
                <td align="right" style="vertical-align:middle;">
                  <p style="margin:0;font-size:9px;font-weight:600;letter-spacing:0.22em;text-transform:uppercase;color:{GOLD};font-family:'DM Sans',Arial,sans-serif;">RÉIA Accounts</p>
                </td>
              </tr>
            </table>
          </td>
        </tr>

      </table>
    </td></tr>
  </table>

</body>
</html>"""

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"Refund Reminder — {len(pending_records)} pending · ₹{total:,.0f} outstanding"
        msg["From"]    = f"RÉIA Accounts <{sender}>"
        msg["To"]      = recipient
        msg.attach(MIMEText(html_content, "html"))

        raw     = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        service = _get_gmail_service()
        service.users().messages().send(
            userId="me",
            body={"raw": raw}
        ).execute()

        print(f"[Scheduler] Email sent to {recipient} via Gmail API ✅")

    except Exception as e:
        print(f"[Scheduler] Gmail API error: {e}")


# ── Main loop ─────────────────────────────────────────────────────────────────

def _scheduler_loop():
    print("[Scheduler] Started.")
    last_sent = 0.0

    while True:
        try:
            settings = load_settings()

            if not settings.get("reminder_enabled", True):
                time.sleep(60)
                continue

            interval_minutes = max(1, int(settings.get("reminder_interval_minutes", 240)))
            interval_seconds = interval_minutes * 60
            recipient        = str(settings.get("reminder_email", "")).strip()
            now              = time.time()

            if recipient and (now - last_sent) >= interval_seconds:
                records = _load_records()

                pending = [
                    r for r in records
                    if str(r.get("status", "")).strip().lower() != "completed"
                ]

                # Always compute fresh days before sending
                for r in pending:
                    r["days_out"] = _compute_days(r)

                print(f"[Scheduler] Pending={len(pending)}, interval={interval_minutes}min")

                if pending:
                    send_reminder_email(pending, recipient, interval_minutes)
                else:
                    print("[Scheduler] No pending refunds — skipping.")

                last_sent = time.time()

            time.sleep(30)

        except Exception as e:
            print(f"[Scheduler] Loop error: {e}")
            time.sleep(60)


def start_scheduler():
    threading.Thread(target=_scheduler_loop, daemon=True).start()
    print("[Scheduler] Thread launched.")

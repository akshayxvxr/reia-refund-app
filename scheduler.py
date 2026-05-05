"""
scheduler.py — Background email reminder scheduler.

- No circular import from app.py
- Sleeps in 30s chunks so interval changes apply quickly
- Minimal REIA-branded HTML email
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
    try:
        d = datetime.strptime(str(record.get("date", "")), "%Y-%m-%d").date()
        return (date.today() - d).days
    except Exception:
        try:
            d = datetime.strptime(str(record.get("date", "")), "%m/%d/%Y").date()
            return (date.today() - d).days
        except Exception:
            return record.get("days_out", 0)


def _get_gmail_service():
    """Build Gmail API service using OAuth2 refresh token."""
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

    # Always recompute days from date so it's never 0
    for r in pending_records:
        r["days_out"] = _compute_days(r)

    total   = sum(r.get("net", 0) for r in pending_records)
    now_str = datetime.now().strftime("%d %b %Y, %I:%M %p")

    rows_html = ""
    for r in pending_records:
        days     = r.get("days_out", 0)
        overdue_label = f"{days} day{'s' if days != 1 else ''}"
        overdue_color = "#C0392B" if days >= 7 else "#92702A"
        rows_html += f"""
        <tr>
          <td style="padding:14px 20px;border-bottom:1px solid #F0EBE3;font-size:13px;color:#6B6560;">{r.get('no','')}</td>
          <td style="padding:14px 20px;border-bottom:1px solid #F0EBE3;">
            <div style="font-size:13px;color:#1A1612;font-weight:600;">{r.get('name','')}</div>
            <div style="font-size:11px;color:#9A8F82;margin-top:2px;">{r.get('store','')}</div>
          </td>
          <td style="padding:14px 20px;border-bottom:1px solid #F0EBE3;font-size:14px;color:#1A1612;font-weight:600;">&#8377;{r.get('net',0):,.0f}</td>
          <td style="padding:14px 20px;border-bottom:1px solid #F0EBE3;">
            <span style="font-size:12px;font-weight:600;color:{overdue_color};">{overdue_label}</span>
          </td>
        </tr>"""

    html_content = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1.0">
</head>
<body style="margin:0;padding:0;background:#F7F4F0;font-family:Arial,Helvetica,sans-serif;">

  <table width="100%" cellpadding="0" cellspacing="0" style="background:#F7F4F0;padding:48px 20px;">
    <tr><td align="center">
      <table width="560" cellpadding="0" cellspacing="0" style="max-width:560px;width:100%;background:#FFFFFF;border-radius:4px;overflow:hidden;">

        <!-- Header -->
        <tr>
          <td style="background:#0E0C07;padding:32px 40px;text-align:center;">
            <img src="{LOGO_URL}" alt="RÉIA" height="32" style="height:32px;display:inline-block;">
            <div style="margin-top:16px;height:1px;background:linear-gradient(90deg,transparent,#C9A96E 30%,#C9A96E 70%,transparent);"></div>
            <p style="margin:14px 0 0;font-size:11px;letter-spacing:0.3em;text-transform:uppercase;color:#C9A96E;">Refund Reminder</p>
          </td>
        </tr>

        <!-- Summary bar -->
        <tr>
          <td style="background:#FAF7F3;padding:20px 40px;border-bottom:1px solid #F0EBE3;">
            <table width="100%" cellpadding="0" cellspacing="0">
              <tr>
                <td>
                  <p style="margin:0;font-size:11px;letter-spacing:0.12em;text-transform:uppercase;color:#9A8F82;">Outstanding Amount</p>
                  <p style="margin:6px 0 0;font-size:22px;color:#0E0C07;font-weight:700;">&#8377;{total:,.0f}</p>
                </td>
                <td align="right">
                  <p style="margin:0;font-size:11px;letter-spacing:0.12em;text-transform:uppercase;color:#9A8F82;">Pending Refunds</p>
                  <p style="margin:6px 0 0;font-size:22px;color:#0E0C07;font-weight:700;">{len(pending_records)}</p>
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- Table header -->
        <tr>
          <td style="padding:0;">
            <table width="100%" cellpadding="0" cellspacing="0">
              <tr style="background:#FAF7F3;">
                <th style="padding:10px 20px;text-align:left;font-size:10px;letter-spacing:0.15em;text-transform:uppercase;color:#B0A898;font-weight:600;border-bottom:1px solid #F0EBE3;">#</th>
                <th style="padding:10px 20px;text-align:left;font-size:10px;letter-spacing:0.15em;text-transform:uppercase;color:#B0A898;font-weight:600;border-bottom:1px solid #F0EBE3;">Customer</th>
                <th style="padding:10px 20px;text-align:left;font-size:10px;letter-spacing:0.15em;text-transform:uppercase;color:#B0A898;font-weight:600;border-bottom:1px solid #F0EBE3;">Net Refund</th>
                <th style="padding:10px 20px;text-align:left;font-size:10px;letter-spacing:0.15em;text-transform:uppercase;color:#B0A898;font-weight:600;border-bottom:1px solid #F0EBE3;">Days Overdue</th>
              </tr>
              {rows_html}
            </table>
          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td style="padding:24px 40px;background:#FAF7F3;border-top:1px solid #F0EBE3;">
            <table width="100%" cellpadding="0" cellspacing="0">
              <tr>
                <td>
                  <p style="margin:0;font-size:11px;color:#B0A898;">Generated {now_str}</p>
                  <p style="margin:4px 0 0;font-size:11px;color:#B0A898;">Reminder frequency: every {interval} minute(s)</p>
                </td>
                <td align="right" style="vertical-align:bottom;">
                  <p style="margin:0;font-size:10px;letter-spacing:0.2em;text-transform:uppercase;color:#C9A96E;">RÉIA Accounts</p>
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

                # Compute fresh days for each pending record
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

"""
scheduler.py — Background email reminder scheduler.

- No circular import from app.py
- Sleeps in 30s chunks so interval changes apply quickly
- Beautiful REIA-branded HTML email
- Sends via Gmail SMTP (no SendGrid)
"""

import threading
import time
import os
import json
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import date, datetime

from settings import load_settings
from google_sheets import GoogleSheetsSync

DATA_FILE = "data/refunds.json"
LOGO_URL  = "https://reia-refund-app.onrender.com/static/reia_logo.png"


# ── Standalone helpers (no import from app.py) ────────────────────────────────

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
    if str(record.get("status", "")).strip().lower() == "completed":
        return 0
    try:
        d = datetime.strptime(str(record.get("date", "")), "%Y-%m-%d").date()
        return (date.today() - d).days
    except Exception:
        return record.get("days_out", 0)


# ── Email ─────────────────────────────────────────────────────────────────────

def send_reminder_email(pending_records: list, recipient: str, interval: int):
    gmail_user     = os.getenv("GMAIL_USER")
    gmail_password = os.getenv("GMAIL_APP_PASSWORD")

    if not gmail_user or not gmail_password:
        print("[Scheduler] GMAIL_USER or GMAIL_APP_PASSWORD not set — skipping.")
        return

    total   = sum(r.get("net", 0) for r in pending_records)
    now_str = datetime.now().strftime("%d %b %Y, %I:%M %p")

    rows_html = ""
    for r in pending_records:
        days      = r.get("days_out", 0)
        age_color = "#C0392B" if days >= 7 else "#5C6B5D"
        age_bg    = "#FEF2F2" if days >= 7 else "#F4F7F4"
        rows_html += f"""
        <tr>
          <td style="padding:14px 16px;border-bottom:1px solid #EDE8DF;font-size:13px;color:#8A7F72;font-weight:500;">{r.get('no','')}</td>
          <td style="padding:14px 16px;border-bottom:1px solid #EDE8DF;font-size:13px;color:#1A1612;font-weight:500;">{r.get('name','')}</td>
          <td style="padding:14px 16px;border-bottom:1px solid #EDE8DF;font-size:13px;color:#5C5347;">{r.get('store','')}</td>
          <td style="padding:14px 16px;border-bottom:1px solid #EDE8DF;font-size:13px;color:#1A1612;font-weight:600;font-family:Georgia,serif;">&#8377;{r.get('net',0):,.0f}</td>
          <td style="padding:14px 16px;border-bottom:1px solid #EDE8DF;">
            <span style="display:inline-block;padding:3px 10px;border-radius:20px;font-size:11px;font-weight:600;color:{age_color};background:{age_bg};letter-spacing:0.04em;">{days}d</span>
          </td>
          <td style="padding:14px 16px;border-bottom:1px solid #EDE8DF;">
            <span style="display:inline-block;padding:3px 10px;border-radius:4px;font-size:11px;font-weight:600;color:#92702A;background:#FDF6E3;letter-spacing:0.06em;text-transform:uppercase;">Pending</span>
          </td>
        </tr>"""

    html_content = f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#F2EDE4;font-family:Georgia,'Times New Roman',serif;">

  <table width="100%" cellpadding="0" cellspacing="0" style="background:#F2EDE4;padding:40px 20px;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;">

        <!-- Logo header -->
        <tr>
          <td style="background:#111008;border-radius:12px 12px 0 0;padding:28px 40px;text-align:center;">
            <img src="{LOGO_URL}" alt="RÉIA" height="36" style="height:36px;display:inline-block;">
          </td>
        </tr>

        <!-- Gold divider -->
        <tr>
          <td style="background:#111008;padding:0 40px;">
            <div style="height:1px;background:linear-gradient(90deg,transparent,#C9A96E,transparent);"></div>
          </td>
        </tr>

        <!-- Title band -->
        <tr>
          <td style="background:#111008;padding:18px 40px 28px;text-align:center;">
            <p style="margin:0;font-size:10px;letter-spacing:0.25em;text-transform:uppercase;color:#C9A96E;font-family:Arial,sans-serif;">Accounts Portal</p>
            <p style="margin:6px 0 0;font-size:18px;color:#F2EDE4;letter-spacing:0.08em;font-weight:400;">Refund Reminder</p>
          </td>
        </tr>

        <!-- Summary cards -->
        <tr>
          <td style="background:#1C1810;padding:24px 40px;">
            <table width="100%" cellpadding="0" cellspacing="0">
              <tr>
                <td width="50%" style="padding-right:8px;">
                  <div style="background:#252016;border:1px solid #3A3020;border-radius:8px;padding:16px 20px;text-align:center;">
                    <p style="margin:0;font-size:10px;letter-spacing:0.15em;text-transform:uppercase;color:#8A7F6A;font-family:Arial,sans-serif;">Outstanding</p>
                    <p style="margin:8px 0 0;font-size:24px;color:#C9A96E;font-weight:400;">&#8377;{total:,.0f}</p>
                  </div>
                </td>
                <td width="50%" style="padding-left:8px;">
                  <div style="background:#252016;border:1px solid #3A3020;border-radius:8px;padding:16px 20px;text-align:center;">
                    <p style="margin:0;font-size:10px;letter-spacing:0.15em;text-transform:uppercase;color:#8A7F6A;font-family:Arial,sans-serif;">Pending Refunds</p>
                    <p style="margin:8px 0 0;font-size:24px;color:#F2EDE4;font-weight:400;">{len(pending_records)}</p>
                  </div>
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- Table -->
        <tr>
          <td style="background:#FFFFFF;padding:0;">
            <table width="100%" cellpadding="0" cellspacing="0">
              <tr style="background:#F7F3EE;">
                <th style="padding:11px 16px;text-align:left;font-size:10px;letter-spacing:0.12em;text-transform:uppercase;color:#9A8F82;font-weight:600;font-family:Arial,sans-serif;border-bottom:1px solid #EDE8DF;">#</th>
                <th style="padding:11px 16px;text-align:left;font-size:10px;letter-spacing:0.12em;text-transform:uppercase;color:#9A8F82;font-weight:600;font-family:Arial,sans-serif;border-bottom:1px solid #EDE8DF;">Customer</th>
                <th style="padding:11px 16px;text-align:left;font-size:10px;letter-spacing:0.12em;text-transform:uppercase;color:#9A8F82;font-weight:600;font-family:Arial,sans-serif;border-bottom:1px solid #EDE8DF;">Store</th>
                <th style="padding:11px 16px;text-align:left;font-size:10px;letter-spacing:0.12em;text-transform:uppercase;color:#9A8F82;font-weight:600;font-family:Arial,sans-serif;border-bottom:1px solid #EDE8DF;">Net Refund</th>
                <th style="padding:11px 16px;text-align:left;font-size:10px;letter-spacing:0.12em;text-transform:uppercase;color:#9A8F82;font-weight:600;font-family:Arial,sans-serif;border-bottom:1px solid #EDE8DF;">Age</th>
                <th style="padding:11px 16px;text-align:left;font-size:10px;letter-spacing:0.12em;text-transform:uppercase;color:#9A8F82;font-weight:600;font-family:Arial,sans-serif;border-bottom:1px solid #EDE8DF;">Status</th>
              </tr>
              {rows_html}
            </table>
          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td style="background:#F7F3EE;border-radius:0 0 12px 12px;padding:20px 40px;border-top:1px solid #EDE8DF;">
            <table width="100%" cellpadding="0" cellspacing="0">
              <tr>
                <td>
                  <p style="margin:0;font-size:11px;color:#9A8F82;font-family:Arial,sans-serif;">
                    {now_str} &nbsp;·&nbsp; Every {interval} minute(s)
                  </p>
                </td>
                <td align="right">
                  <p style="margin:0;font-size:11px;color:#C9A96E;font-family:Arial,sans-serif;letter-spacing:0.1em;">RÉIA ACCOUNTS</p>
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
        msg["Subject"] = f"Refund Reminder — {len(pending_records)} pending, Rs.{total:,.0f} outstanding"
        msg["From"]    = f"RÉIA Accounts <{gmail_user}>"
        msg["To"]      = recipient
        msg.attach(MIMEText(html_content, "html"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(gmail_user, gmail_password)
            server.sendmail(gmail_user, recipient, msg.as_string())

        print(f"[Scheduler] Email sent to {recipient} via Gmail SMTP")
    except Exception as e:
        print(f"[Scheduler] Gmail SMTP error: {e}")


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
                for r in records:
                    r["days_out"] = _compute_days(r)

                pending = [
                    r for r in records
                    if str(r.get("status", "")).strip().lower() != "completed"
                ]

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

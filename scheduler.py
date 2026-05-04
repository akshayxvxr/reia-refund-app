"""
scheduler.py — Background email reminder scheduler.

Fixes:
  - No circular import from app.py
  - Reads interval dynamically every tick
  - Sleeps in short chunks so interval changes take effect quickly
"""

import threading
import time
import os
import json
from datetime import date, datetime

import sendgrid
from sendgrid.helpers.mail import Mail

from settings import load_settings
from google_sheets import GoogleSheetsSync

DATA_FILE = "data/refunds.json"


# ── Standalone record helpers (NO import from app.py) ────────────────────────

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
    sg_key = os.getenv("SENDGRID_API_KEY")
    if not sg_key:
        print("[Scheduler] SENDGRID_API_KEY not set — skipping email.")
        return

    from_email = os.getenv("SENDGRID_FROM_EMAIL", "noreply@reia.com")

    rows_html = ""
    for r in pending_records:
        days      = r.get("days_out", 0)
        highlight = ' style="color:#dc2626;font-weight:bold;"' if days >= 7 else ""
        rows_html += f"""
        <tr>
          <td style="padding:6px 10px;border-bottom:1px solid #e5e7eb;">{r.get('no','')}</td>
          <td style="padding:6px 10px;border-bottom:1px solid #e5e7eb;">{r.get('name','')}</td>
          <td style="padding:6px 10px;border-bottom:1px solid #e5e7eb;">{r.get('store','')}</td>
          <td style="padding:6px 10px;border-bottom:1px solid #e5e7eb;">₹{r.get('net',0):,.0f}</td>
          <td style="padding:6px 10px;border-bottom:1px solid #e5e7eb;"{highlight}>{days} days</td>
        </tr>"""

    total = sum(r.get("net", 0) for r in pending_records)

    html_content = f"""
    <div style="font-family:Arial,sans-serif;max-width:640px;margin:auto;">
      <h2 style="background:#b8860b;color:#fff;padding:14px 20px;border-radius:6px 6px 0 0;margin:0;">
        REIA Refund Reminder
      </h2>
      <div style="background:#fffbeb;padding:16px 20px;border:1px solid #e5e7eb;border-top:none;">
        <p style="margin:0 0 8px;">
          <strong>{len(pending_records)}</strong> refund(s) pending.
          Total outstanding: <strong>₹{total:,.0f}</strong>
        </p>
        <p style="margin:0;font-size:12px;color:#6b7280;">
          Reminders sent every <strong>{interval} minute(s)</strong>.
        </p>
      </div>
      <table style="width:100%;border-collapse:collapse;border:1px solid #e5e7eb;border-top:none;">
        <thead style="background:#f3f4f6;">
          <tr>
            <th style="padding:8px 10px;text-align:left;">#</th>
            <th style="padding:8px 10px;text-align:left;">Name</th>
            <th style="padding:8px 10px;text-align:left;">Store</th>
            <th style="padding:8px 10px;text-align:left;">Net Refund</th>
            <th style="padding:8px 10px;text-align:left;">Days Pending</th>
          </tr>
        </thead>
        <tbody>{rows_html}</tbody>
      </table>
      <p style="font-size:11px;color:#9ca3af;padding:12px 20px;border:1px solid #e5e7eb;border-top:none;margin:0;">
        Sent on {datetime.now().strftime('%d %b %Y, %I:%M %p')} · REIA Refund Tracker
      </p>
    </div>
    """

    try:
        sg       = sendgrid.SendGridAPIClient(api_key=sg_key)
        response = sg.send(Mail(
            from_email=from_email,
            to_emails=recipient,
            subject=f"[REIA] {len(pending_records)} Pending Refund(s) — ₹{total:,.0f} Outstanding",
            html_content=html_content,
        ))
        print(f"[Scheduler] Email sent to {recipient} — HTTP {response.status_code}")
    except Exception as e:
        print(f"[Scheduler] SendGrid error: {e}")


# ── Main loop ─────────────────────────────────────────────────────────────────

def _scheduler_loop():
    print("[Scheduler] Started.")

    # Track when the last email was sent so we respect the interval correctly
    last_sent = 0.0

    while True:
        try:
            settings = load_settings()

            if not settings.get("reminder_enabled", True):
                # Disabled — check again in 1 minute
                time.sleep(60)
                continue

            interval_minutes = max(1, int(settings.get("reminder_interval_minutes", 240)))
            interval_seconds = interval_minutes * 60
            recipient        = str(settings.get("reminder_email", "")).strip()

            now = time.time()

            if recipient and (now - last_sent) >= interval_seconds:
                # Time to send
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
                    print("[Scheduler] No pending refunds — skipping email.")

                last_sent = time.time()

            # Sleep in 30-second chunks so interval changes are picked up quickly
            time.sleep(30)

        except Exception as e:
            print(f"[Scheduler] Loop error: {e}")
            time.sleep(60)


def start_scheduler():
    t = threading.Thread(target=_scheduler_loop, daemon=True)
    t.start()
    print("[Scheduler] Thread launched.")
    
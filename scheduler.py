"""
scheduler.py — Background email reminder scheduler.

Reads reminder_interval_minutes from settings.json at runtime,
so any change made in the Settings UI takes effect on the *next* tick
without restarting the server.
"""

import threading
import time
import os
import json
from datetime import date, datetime

import sendgrid
from sendgrid.helpers.mail import Mail

from settings import load_settings


# ── email helper ──────────────────────────────────────────────────────────────

def send_reminder_email(pending_records: list, recipient: str):
    """Send a summary email of all pending refunds."""
    sg_key = os.getenv("SENDGRID_API_KEY")
    if not sg_key:
        print("[Scheduler] SENDGRID_API_KEY not set — skipping email.")
        return

    from_email = os.getenv("SENDGRID_FROM_EMAIL", "noreply@reia.com")

    rows_html = ""
    for r in pending_records:
        days = r.get("days_out", 0)
        highlight = ' style="color:#dc2626;font-weight:bold;"' if days >= 7 else ""
        rows_html += f"""
        <tr>
          <td style="padding:6px 10px;border-bottom:1px solid #e5e7eb;">{r.get('no','')}</td>
          <td style="padding:6px 10px;border-bottom:1px solid #e5e7eb;">{r.get('name','')}</td>
          <td style="padding:6px 10px;border-bottom:1px solid #e5e7eb;">{r.get('store','')}</td>
          <td style="padding:6px 10px;border-bottom:1px solid #e5e7eb;">₹{r.get('net',0):,.0f}</td>
          <td style="padding:6px 10px;border-bottom:1px solid #e5e7eb;"{highlight}>{days} days</td>
        </tr>"""

    total_outstanding = sum(r.get("net", 0) for r in pending_records)
    settings = load_settings()
    interval = settings.get("reminder_interval_minutes", 240)

    html_content = f"""
    <div style="font-family:Arial,sans-serif;max-width:640px;margin:auto;">
      <h2 style="background:#b8860b;color:#fff;padding:14px 20px;border-radius:6px 6px 0 0;margin:0;">
        REIA Refund Reminder
      </h2>
      <div style="background:#fffbeb;padding:16px 20px;border:1px solid #e5e7eb;border-top:none;">
        <p style="margin:0 0 8px;">
          <strong>{len(pending_records)}</strong> refund(s) are still pending.
          Total outstanding: <strong>₹{total_outstanding:,.0f}</strong>
        </p>
        <p style="margin:0;font-size:12px;color:#6b7280;">
          Reminders are sent every <strong>{interval} minute(s)</strong>.
          Change this in <em>Settings → Reminder Interval</em>.
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
        Sent on {datetime.now().strftime('%d %b %Y, %I:%M %p')} by REIA Refund Tracker
      </p>
    </div>
    """

    message = Mail(
        from_email=from_email,
        to_emails=recipient,
        subject=f"[REIA] {len(pending_records)} Pending Refund(s) — ₹{total_outstanding:,.0f} Outstanding",
        html_content=html_content,
    )

    try:
        sg = sendgrid.SendGridAPIClient(api_key=sg_key)
        response = sg.send(message)
        print(f"[Scheduler] Reminder sent to {recipient} — status {response.status_code}")
    except Exception as e:
        print(f"[Scheduler] SendGrid error: {e}")


# ── main loop ─────────────────────────────────────────────────────────────────

def _scheduler_loop():
    print("[Scheduler] Started — will read interval from settings dynamically.")
    while True:
        settings = load_settings()

        if not settings.get("reminder_enabled", True):
            # Disabled — sleep 1 min and re-check
            time.sleep(60)
            continue

        interval_minutes = max(1, int(settings.get("reminder_interval_minutes", 240)))
        recipient = settings.get("reminder_email", "").strip() or os.getenv("REMINDER_EMAIL", "")

        if recipient:
            # Import here to avoid circular imports at module load time
            try:
                from app import load_records, compute_days
                records = load_records()
                for r in records:
                    r["days_out"] = compute_days(r)
                pending = [r for r in records if r.get("status") not in ("Completed",)]
                if pending:
                    send_reminder_email(pending, recipient)
                else:
                    print("[Scheduler] No pending refunds — skipping email.")
            except Exception as e:
                print(f"[Scheduler] Error loading records: {e}")
        else:
            print("[Scheduler] No recipient configured. Set REMINDER_EMAIL env var or via Settings.")

        # Sleep for the configured interval
        print(f"[Scheduler] Next reminder in {interval_minutes} minute(s).")
        time.sleep(interval_minutes * 60)


def start_scheduler():
    t = threading.Thread(target=_scheduler_loop, daemon=True)
    t.start()

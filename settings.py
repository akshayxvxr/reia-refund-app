"""
settings.py — Loads/saves reminder settings.

Priority:
  1. Google Sheets "App Settings" tab  (persistent across deploys)
  2. Local data/settings.json          (fallback if Sheets not configured)
"""

import json
import os
from google_sheets import GoogleSheetsSync

SETTINGS_FILE = "data/settings.json"

DEFAULTS = {
    "reminder_interval_minutes": 240,
    "reminder_enabled": True,
    "reminder_email": os.getenv("REMINDER_EMAIL", ""),
}

# Single shared instance — reuses the same connection as app.py
_gs = GoogleSheetsSync()


def _load_local() -> dict:
    settings = dict(DEFAULTS)
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE) as f:
                data = json.load(f)
            for k, v in DEFAULTS.items():
                data.setdefault(k, v)
            return data
        except Exception:
            pass
    return settings


def _save_local(settings: dict):
    os.makedirs("data", exist_ok=True)
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f, indent=2)


def load_settings() -> dict:
    if _gs.is_configured():
        try:
            return _gs.load_settings()
        except Exception as e:
            print(f"[Settings] Sheets read failed: {e} — using local fallback")
    return _load_local()


def save_settings(settings: dict):
    if _gs.is_configured():
        try:
            _gs.save_settings(settings)
            # Also save locally as backup
            _save_local(settings)
            return
        except Exception as e:
            print(f"[Settings] Sheets write failed: {e} — saving locally only")
    _save_local(settings)
    
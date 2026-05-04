import json
import os

SETTINGS_FILE = "data/settings.json"

DEFAULTS = {
    "reminder_interval_minutes": 240,  # 4 hours default
    "reminder_enabled": True,
    "reminder_email": os.getenv("REMINDER_EMAIL", ""),  # fallback recipient
}


def load_settings() -> dict:
    if not os.path.exists(SETTINGS_FILE):
        return dict(DEFAULTS)
    try:
        with open(SETTINGS_FILE) as f:
            data = json.load(f)
        # Fill in any missing keys with defaults
        for k, v in DEFAULTS.items():
            data.setdefault(k, v)
        return data
    except Exception:
        return dict(DEFAULTS)


def save_settings(settings: dict):
    os.makedirs("data", exist_ok=True)
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f, indent=2)

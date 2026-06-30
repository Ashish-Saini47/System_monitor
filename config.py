"""Configuration for the activity tracker. Loads/saves config.json next to the app."""
import json
import os

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DATA_DIR = os.path.join(APP_DIR, "data")
CONFIG_PATH = os.path.join(APP_DIR, "config.json")

DEFAULTS = {
    "data_dir": DEFAULT_DATA_DIR,
    # how often (seconds) to sample the foreground window
    "foreground_poll_sec": 3,
    # how often (seconds) to check lock/unlock state
    "lock_poll_sec": 1,
    # how often (seconds) to take a periodic screenshot
    "screenshot_interval_sec": 300,
    # feature toggles
    "enable_app_usage": True,
    "enable_session_events": True,
    "enable_periodic_screenshots": True,
    "enable_unlock_photo": True,
    "enable_unlock_screenshot": True,
    # webcam
    "camera_index": 0,
    # mean grayscale brightness below this => treat as "camera covered"
    "covered_brightness_threshold": 12.0,
    # telegram notifications on unlock
    "enable_telegram": False,
    "telegram_token": "",
    "telegram_chat_id": "",
    # retention: delete captured images older than this many days (0 = keep forever)
    "retention_days": 7,
    # periodic/unlock screenshots: JPEG quality and max width (downscaled)
    "screenshot_jpeg_quality": 70,
    "screenshot_max_width": 1280,
}


def load_config():
    cfg = dict(DEFAULTS)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg.update(json.load(f))
        except Exception:
            pass
    # make sure data dir exists
    os.makedirs(cfg["data_dir"], exist_ok=True)
    os.makedirs(os.path.join(cfg["data_dir"], "screenshots"), exist_ok=True)
    os.makedirs(os.path.join(cfg["data_dir"], "unlock_photos"), exist_ok=True)
    return cfg


def save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)

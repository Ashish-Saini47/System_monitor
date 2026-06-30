"""Background monitoring. Runs three daemon threads and writes to the DB.

Threads:
  1. foreground loop  -> records app/window usage segments
  2. lock-state loop  -> detects lock/unlock; on unlock fires webcam + screenshot
  3. screenshot loop  -> periodic screenshots while unlocked

Qt signals notify the UI to refresh. Signals are safe to emit from worker
threads; connected slots run on the receiving (GUI) thread.
"""
import os
import threading
import time
from datetime import datetime, timedelta

from PySide6.QtCore import QObject, Signal

import capture
import winutils
from database import now_iso
from notifier import TelegramNotifier


class Monitor(QObject):
    data_changed = Signal()
    status_changed = Signal(str)
    activity = Signal(str)  # short human-readable log line for the status area

    def __init__(self, db, cfg):
        super().__init__()
        self.db = db
        self.cfg = cfg
        self._stop = threading.Event()
        self._threads = []
        self.running = False
        self.notifier = TelegramNotifier(
            cfg.get("telegram_token", ""), cfg.get("telegram_chat_id", "")
        )

    # ---- lifecycle -----------------------------------------------------
    def start(self):
        if self.running:
            return
        if not winutils.is_windows():
            self.activity.emit(
                "WARNING: not running on Windows — monitoring will be inactive."
            )
        self._stop.clear()
        self.running = True
        self.notifier = TelegramNotifier(
            self.cfg.get("telegram_token", ""), self.cfg.get("telegram_chat_id", "")
        )
        self.db.add_event("monitor_start")

        self._threads = []
        if self.cfg.get("enable_app_usage", True):
            self._threads.append(threading.Thread(target=self._foreground_loop, daemon=True))
        if self.cfg.get("enable_session_events", True) or self.cfg.get("enable_unlock_photo", True):
            self._threads.append(threading.Thread(target=self._lock_loop, daemon=True))
        if self.cfg.get("enable_periodic_screenshots", True):
            self._threads.append(threading.Thread(target=self._screenshot_loop, daemon=True))
        # retention always runs (cheap) to keep disk bounded
        self._threads.append(threading.Thread(target=self._retention_loop, daemon=True))
        for t in self._threads:
            t.start()

        self.status_changed.emit("Monitoring")
        self.activity.emit("Monitoring started.")
        self.data_changed.emit()

    def stop(self):
        if not self.running:
            return
        self._stop.set()
        for t in self._threads:
            t.join(timeout=3)
        self._threads = []
        self.running = False
        self.db.add_event("monitor_stop")
        self.status_changed.emit("Stopped")
        self.activity.emit("Monitoring stopped.")
        self.data_changed.emit()

    # ---- worker loops --------------------------------------------------
    def _foreground_loop(self):
        poll = max(1, int(self.cfg.get("foreground_poll_sec", 3)))
        cur_app, cur_title = winutils.get_foreground()
        start = now_iso()
        start_mono = time.monotonic()

        while not self._stop.is_set():
            time.sleep(poll)
            if winutils.is_locked():
                continue  # don't attribute locked time to any app
            app, title = winutils.get_foreground()
            if (app, title) != (cur_app, cur_title):
                seconds = time.monotonic() - start_mono
                if cur_app and seconds >= 1:
                    self.db.add_usage(cur_app, cur_title, start, now_iso(), seconds)
                    self.data_changed.emit()
                cur_app, cur_title = app, title
                start = now_iso()
                start_mono = time.monotonic()

        # flush the final segment on stop
        seconds = time.monotonic() - start_mono
        if cur_app and seconds >= 1:
            self.db.add_usage(cur_app, cur_title, start, now_iso(), seconds)
            self.data_changed.emit()

    def _lock_loop(self):
        poll = max(1, int(self.cfg.get("lock_poll_sec", 1)))
        prev_locked = winutils.is_locked()  # init without firing

        while not self._stop.is_set():
            time.sleep(poll)
            locked = winutils.is_locked()
            if locked == prev_locked:
                continue

            if locked:  # unlocked -> locked
                if self.cfg.get("enable_session_events", True):
                    self.db.add_event("lock")
                    self.activity.emit("Workstation locked.")
                    self.data_changed.emit()
            else:  # locked -> unlocked  (someone just got in)
                if self.cfg.get("enable_session_events", True):
                    self.db.add_event("unlock")
                    self.activity.emit("Workstation unlocked.")
                self._on_unlock()
                self.data_changed.emit()
            prev_locked = locked

    def _on_unlock(self):
        # give the desktop a beat to come up before grabbing the camera
        time.sleep(1.0)
        photo_path, covered = None, False
        if self.cfg.get("enable_unlock_photo", True):
            photo_path, brightness, covered = capture.capture_webcam(
                self.cfg["data_dir"],
                camera_index=int(self.cfg.get("camera_index", 0)),
                covered_threshold=float(self.cfg.get("covered_brightness_threshold", 12.0)),
            )
            self.db.add_unlock_photo(photo_path, covered, brightness)
            if covered:
                self.activity.emit("Unlock photo: CAMERA COVERED (flagged).")
            elif photo_path:
                self.activity.emit("Unlock photo captured.")
            else:
                self.activity.emit("Unlock photo: capture failed.")
        if self.cfg.get("enable_unlock_screenshot", True):
            sp = capture.capture_screenshot(
                self.cfg["data_dir"], kind="unlock",
                max_width=int(self.cfg.get("screenshot_max_width", 1280)),
                quality=int(self.cfg.get("screenshot_jpeg_quality", 70)),
            )
            if sp:
                self.db.add_screenshot(sp, "unlock")
        if self.cfg.get("enable_telegram", False):
            self._notify_unlock(photo_path, covered)

    def _notify_unlock(self, photo_path, covered):
        if not self.notifier.enabled:
            return

        def _send():
            ts = now_iso().replace("T", " ")
            if covered:
                text = f"\u26a0\ufe0f Laptop UNLOCKED at {ts}\nCamera was COVERED \u2014 no usable photo."
            else:
                text = f"\U0001f513 Laptop unlocked at {ts}"
            if photo_path and not covered:
                ok, msg = self.notifier.send_photo(photo_path, caption=text)
            else:
                ok, msg = self.notifier.send_message(text)
            self.activity.emit("Telegram: notification sent." if ok else f"Telegram failed: {msg}")

        threading.Thread(target=_send, daemon=True).start()

    def _screenshot_loop(self):
        interval = max(10, int(self.cfg.get("screenshot_interval_sec", 300)))
        elapsed = 0
        while not self._stop.is_set():
            time.sleep(1)
            elapsed += 1
            if elapsed < interval:
                continue
            elapsed = 0
            if winutils.is_locked():
                continue  # skip — would only capture the lock screen
            sp = capture.capture_screenshot(
                self.cfg["data_dir"], kind="periodic",
                max_width=int(self.cfg.get("screenshot_max_width", 1280)),
                quality=int(self.cfg.get("screenshot_jpeg_quality", 70)),
            )
            if sp:
                self.db.add_screenshot(sp, "periodic")
                self.data_changed.emit()

    def _retention_loop(self):
        self._cleanup_once()
        while not self._stop.is_set():
            # check roughly every 6 hours, but stay responsive to stop
            for _ in range(6 * 3600):
                if self._stop.is_set():
                    return
                time.sleep(1)
            self._cleanup_once()

    def _cleanup_once(self):
        days = int(self.cfg.get("retention_days", 7))
        if days <= 0:
            return  # keep forever
        cutoff = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
        paths = self.db.purge_images_before(cutoff)
        removed = 0
        for p in paths:
            try:
                if p and os.path.exists(p):
                    os.remove(p)
                    removed += 1
            except Exception:
                pass
        if removed:
            self.activity.emit(f"Retention: removed {removed} image(s) older than {days} days.")
            self.data_changed.emit()

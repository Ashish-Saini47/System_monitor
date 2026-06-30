"""Laptop Activity Tracker — PySide6 dashboard.

Run:  python app.py
"""
import os
import sys

from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QPixmap, QFont
from PySide6.QtWidgets import (
    QApplication, QWidget, QMainWindow, QHBoxLayout, QVBoxLayout, QListWidget,
    QListWidgetItem, QStackedWidget, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QScrollArea, QGridLayout, QFrame, QSpinBox,
    QCheckBox, QFormLayout, QMessageBox, QPlainTextEdit, QSizePolicy, QLineEdit,
)

import config as configmod
from database import Database
from monitor import Monitor
from notifier import TelegramNotifier

LIGHT_QSS = """
* { font-family: "Segoe UI", Arial, sans-serif; }
QMainWindow, QWidget { background: #f5f6f8; color: #1f2430; }
#Sidebar { background: #ffffff; border-right: 1px solid #e2e5ea; }
#Sidebar QListWidget { background: transparent; border: none; font-size: 14px; }
#Sidebar QListWidget::item { padding: 11px 16px; border-radius: 6px; margin: 2px 8px; }
#Sidebar QListWidget::item:selected { background: #e8eefc; color: #1d4ed8; }
#Sidebar QListWidget::item:hover { background: #f0f2f6; }
#Brand { font-size: 16px; font-weight: 600; padding: 16px; color: #1f2430; }
#TopBar { background: #ffffff; border-bottom: 1px solid #e2e5ea; }
#StatusDot { font-weight: 600; }
QPushButton#Primary { background: #1d4ed8; color: white; border: none;
    border-radius: 6px; padding: 8px 18px; font-weight: 600; }
QPushButton#Primary:hover { background: #1b46c2; }
QPushButton#Danger { background: #dc2626; color: white; border: none;
    border-radius: 6px; padding: 8px 18px; font-weight: 600; }
QPushButton#Danger:hover { background: #c11f1f; }
QPushButton { background: #eef0f4; border: 1px solid #d8dce3; border-radius: 6px;
    padding: 7px 14px; }
QPushButton:hover { background: #e6e9ef; }
QTableWidget { background: white; border: 1px solid #e2e5ea; border-radius: 8px;
    gridline-color: #eef0f4; }
QHeaderView::section { background: #f7f8fa; border: none;
    border-bottom: 1px solid #e2e5ea; padding: 8px; font-weight: 600; }
QLabel#PageTitle { font-size: 20px; font-weight: 600; padding: 4px 0 12px 0; }
QFrame#Card { background: white; border: 1px solid #e2e5ea; border-radius: 8px; }
QPlainTextEdit { background: white; border: 1px solid #e2e5ea; border-radius: 8px; }
QScrollArea { border: none; background: transparent; }
QCheckBox, QLabel { font-size: 14px; }
"""

THUMB = QSize(220, 150)


def make_title(text):
    lbl = QLabel(text)
    lbl.setObjectName("PageTitle")
    return lbl


class ImageGrid(QWidget):
    """Scrollable grid of image thumbnails with captions."""

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.inner = QWidget()
        self.grid = QGridLayout(self.inner)
        self.grid.setSpacing(14)
        self.grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.scroll.setWidget(self.inner)
        layout.addWidget(self.scroll)

    def set_items(self, items):
        # clear
        while self.grid.count():
            w = self.grid.takeAt(0).widget()
            if w:
                w.deleteLater()
        if not items:
            self.grid.addWidget(QLabel("Nothing captured yet."), 0, 0)
            return
        cols = 4
        for i, (path, caption, flagged) in enumerate(items):
            card = QFrame()
            card.setObjectName("Card")
            cl = QVBoxLayout(card)
            img = QLabel()
            img.setAlignment(Qt.AlignCenter)
            img.setFixedSize(THUMB)
            if path and os.path.exists(path):
                pm = QPixmap(path)
                if not pm.isNull():
                    img.setPixmap(pm.scaled(THUMB, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                else:
                    img.setText("(unreadable)")
            else:
                img.setText("(no image)")
            cap = QLabel(caption)
            cap.setWordWrap(True)
            if flagged:
                cap.setStyleSheet("color:#dc2626; font-weight:600;")
            cl.addWidget(img)
            cl.addWidget(cap)
            self.grid.addWidget(card, i // cols, i % cols)


class Dashboard(QMainWindow):
    def __init__(self, db, cfg):
        super().__init__()
        self.db = db
        self.cfg = cfg
        self.monitor = Monitor(db, cfg)
        self.setWindowTitle("Laptop Activity Tracker")
        self.resize(1100, 720)

        self._build_ui()
        self._wire_monitor()

        # periodic refresh as a fallback to signal-driven refresh
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_current)
        self.timer.start(5000)
        self.refresh_current()

    # ---- UI ------------------------------------------------------------
    def _build_ui(self):
        root = QWidget()
        root_l = QHBoxLayout(root)
        root_l.setContentsMargins(0, 0, 0, 0)
        root_l.setSpacing(0)

        # sidebar
        side = QWidget()
        side.setObjectName("Sidebar")
        side.setFixedWidth(210)
        side_l = QVBoxLayout(side)
        side_l.setContentsMargins(0, 0, 0, 0)
        brand = QLabel("Activity Tracker")
        brand.setObjectName("Brand")
        side_l.addWidget(brand)
        self.nav = QListWidget()
        for name in ["Activity Log", "App Usage", "Unlock Photos", "Screenshots", "Settings"]:
            self.nav.addItem(QListWidgetItem(name))
        self.nav.currentRowChanged.connect(self._on_nav)
        side_l.addWidget(self.nav)
        side_l.addStretch()

        # main column
        main = QWidget()
        main_l = QVBoxLayout(main)
        main_l.setContentsMargins(0, 0, 0, 0)
        main_l.setSpacing(0)

        # top bar
        top = QWidget()
        top.setObjectName("TopBar")
        top.setFixedHeight(58)
        top_l = QHBoxLayout(top)
        top_l.setContentsMargins(18, 0, 18, 0)
        self.status_lbl = QLabel("● Stopped")
        self.status_lbl.setObjectName("StatusDot")
        self.status_lbl.setStyleSheet("color:#dc2626;")
        self.toggle_btn = QPushButton("Start Monitoring")
        self.toggle_btn.setObjectName("Primary")
        self.toggle_btn.clicked.connect(self._toggle_monitor)
        top_l.addWidget(self.status_lbl)
        top_l.addStretch()
        top_l.addWidget(self.toggle_btn)

        # pages
        self.pages = QStackedWidget()
        self.pages.addWidget(self._page_events())
        self.pages.addWidget(self._page_usage())
        self.pages.addWidget(self._page_unlock())
        self.pages.addWidget(self._page_screens())
        self.pages.addWidget(self._page_settings())

        # activity log strip
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setFixedHeight(90)

        body = QWidget()
        body_l = QVBoxLayout(body)
        body_l.setContentsMargins(18, 14, 18, 14)
        body_l.addWidget(self.pages)
        body_l.addWidget(QLabel("Recent activity"))
        body_l.addWidget(self.log)

        main_l.addWidget(top)
        main_l.addWidget(body)

        root_l.addWidget(side)
        root_l.addWidget(main)
        self.setCentralWidget(root)
        self.nav.setCurrentRow(0)

    def _table(self, headers):
        t = QTableWidget(0, len(headers))
        t.setHorizontalHeaderLabels(headers)
        t.verticalHeader().setVisible(False)
        t.setEditTriggers(QTableWidget.NoEditTriggers)
        t.setSelectionBehavior(QTableWidget.SelectRows)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        return t

    def _page_events(self):
        w = QWidget()
        l = QVBoxLayout(w)
        l.addWidget(make_title("Activity Log"))
        self.events_tbl = self._table(["Time", "Event", "Details"])
        l.addWidget(self.events_tbl)
        return w

    def _page_usage(self):
        w = QWidget()
        l = QVBoxLayout(w)
        l.addWidget(make_title("App Usage"))
        self.summary_lbl = QLabel("")
        self.summary_lbl.setWordWrap(True)
        l.addWidget(self.summary_lbl)
        self.usage_tbl = self._table(["App", "Window title", "Start", "End", "Duration"])
        l.addWidget(self.usage_tbl)
        return w

    def _page_unlock(self):
        w = QWidget()
        l = QVBoxLayout(w)
        l.addWidget(make_title("Unlock Photos"))
        hint = QLabel("A webcam photo is taken each time the laptop is unlocked. "
                      "Entries in red mean the camera was covered/blocked at unlock.")
        hint.setWordWrap(True)
        l.addWidget(hint)
        self.unlock_grid = ImageGrid()
        l.addWidget(self.unlock_grid)
        return w

    def _page_screens(self):
        w = QWidget()
        l = QVBoxLayout(w)
        l.addWidget(make_title("Screenshots"))
        self.screen_grid = ImageGrid()
        l.addWidget(self.screen_grid)
        return w

    def _page_settings(self):
        w = QWidget()
        outer = QVBoxLayout(w)
        outer.addWidget(make_title("Settings"))
        card = QFrame()
        card.setObjectName("Card")
        form = QFormLayout(card)
        form.setContentsMargins(20, 20, 20, 20)
        form.setSpacing(12)

        self.s_usage = QCheckBox("Track app / window usage")
        self.s_session = QCheckBox("Log lock / unlock events")
        self.s_periodic = QCheckBox("Periodic screenshots")
        self.s_unlockphoto = QCheckBox("Webcam photo on every unlock")
        self.s_unlockshot = QCheckBox("Screenshot on every unlock")
        for cb, key in [
            (self.s_usage, "enable_app_usage"),
            (self.s_session, "enable_session_events"),
            (self.s_periodic, "enable_periodic_screenshots"),
            (self.s_unlockphoto, "enable_unlock_photo"),
            (self.s_unlockshot, "enable_unlock_screenshot"),
        ]:
            cb.setChecked(bool(self.cfg.get(key, True)))

        self.s_shot_interval = QSpinBox()
        self.s_shot_interval.setRange(10, 86400)
        self.s_shot_interval.setValue(int(self.cfg.get("screenshot_interval_sec", 300)))
        self.s_shot_interval.setSuffix(" sec")

        self.s_fg_poll = QSpinBox()
        self.s_fg_poll.setRange(1, 60)
        self.s_fg_poll.setValue(int(self.cfg.get("foreground_poll_sec", 3)))
        self.s_fg_poll.setSuffix(" sec")

        self.s_cam_idx = QSpinBox()
        self.s_cam_idx.setRange(0, 8)
        self.s_cam_idx.setValue(int(self.cfg.get("camera_index", 0)))

        self.s_cover = QSpinBox()
        self.s_cover.setRange(1, 120)
        self.s_cover.setValue(int(self.cfg.get("covered_brightness_threshold", 12)))

        form.addRow(self.s_usage)
        form.addRow(self.s_session)
        form.addRow(self.s_periodic)
        form.addRow(self.s_unlockphoto)
        form.addRow(self.s_unlockshot)
        form.addRow("Screenshot interval", self.s_shot_interval)
        form.addRow("Foreground poll", self.s_fg_poll)
        form.addRow("Camera index", self.s_cam_idx)
        form.addRow("Covered-camera brightness threshold", self.s_cover)

        # --- storage / retention ---
        self.s_retention = QSpinBox()
        self.s_retention.setRange(0, 365)
        self.s_retention.setValue(int(self.cfg.get("retention_days", 7)))
        self.s_retention.setSuffix(" days  (0 = keep forever)")

        self.s_jpeg_q = QSpinBox()
        self.s_jpeg_q.setRange(20, 95)
        self.s_jpeg_q.setValue(int(self.cfg.get("screenshot_jpeg_quality", 70)))

        self.s_max_w = QSpinBox()
        self.s_max_w.setRange(640, 3840)
        self.s_max_w.setSingleStep(160)
        self.s_max_w.setValue(int(self.cfg.get("screenshot_max_width", 1280)))
        self.s_max_w.setSuffix(" px")

        form.addRow("Keep images for", self.s_retention)
        form.addRow("Screenshot JPEG quality", self.s_jpeg_q)
        form.addRow("Screenshot max width", self.s_max_w)

        # --- Telegram ---
        self.s_telegram = QCheckBox("Send Telegram notification on every unlock")
        self.s_telegram.setChecked(bool(self.cfg.get("enable_telegram", False)))
        self.s_tg_token = QLineEdit(self.cfg.get("telegram_token", ""))
        self.s_tg_token.setPlaceholderText("bot token from @BotFather")
        self.s_tg_token.setEchoMode(QLineEdit.Password)
        self.s_tg_chat = QLineEdit(str(self.cfg.get("telegram_chat_id", "")))
        self.s_tg_chat.setPlaceholderText("your numeric chat id")
        test_btn = QPushButton("Send test message")
        test_btn.clicked.connect(self._test_telegram)

        form.addRow(self.s_telegram)
        form.addRow("Telegram bot token", self.s_tg_token)
        form.addRow("Telegram chat id", self.s_tg_chat)
        form.addRow("", test_btn)

        save = QPushButton("Save settings")
        save.setObjectName("Primary")
        save.clicked.connect(self._save_settings)
        form.addRow(save)

        note = QLabel("Changes apply the next time you start monitoring.")
        note.setStyleSheet("color:#6b7280;")
        outer.addWidget(card)
        outer.addWidget(note)
        outer.addStretch()
        return w

    # ---- monitor glue --------------------------------------------------
    def _wire_monitor(self):
        self.monitor.status_changed.connect(self._on_status)
        self.monitor.activity.connect(self._append_log)
        self.monitor.data_changed.connect(self.refresh_current)

    def _toggle_monitor(self):
        if self.monitor.running:
            self.monitor.stop()
        else:
            self.monitor.start()

    def _on_status(self, text):
        running = text == "Monitoring"
        self.status_lbl.setText(("● " if running else "● ") + text)
        self.status_lbl.setStyleSheet("color:#16a34a;" if running else "color:#dc2626;")
        self.toggle_btn.setText("Stop Monitoring" if running else "Start Monitoring")
        self.toggle_btn.setObjectName("Danger" if running else "Primary")
        self.toggle_btn.setStyle(self.toggle_btn.style())  # re-polish for new objectName
        self.setStyleSheet(LIGHT_QSS)

    def _append_log(self, line):
        from datetime import datetime
        self.log.appendPlainText(f"{datetime.now().strftime('%H:%M:%S')}  {line}")

    def _test_telegram(self):
        n = TelegramNotifier(self.s_tg_token.text(), self.s_tg_chat.text())
        if not n.enabled:
            QMessageBox.warning(self, "Telegram", "Enter both a bot token and a chat id first.")
            return
        ok, msg = n.send_message("\u2705 Activity Tracker test message.")
        if ok:
            QMessageBox.information(self, "Telegram", "Test message sent. Check your chat.")
        else:
            QMessageBox.critical(self, "Telegram", f"Failed:\n{msg}")

    def _save_settings(self):
        self.cfg["enable_app_usage"] = self.s_usage.isChecked()
        self.cfg["enable_session_events"] = self.s_session.isChecked()
        self.cfg["enable_periodic_screenshots"] = self.s_periodic.isChecked()
        self.cfg["enable_unlock_photo"] = self.s_unlockphoto.isChecked()
        self.cfg["enable_unlock_screenshot"] = self.s_unlockshot.isChecked()
        self.cfg["screenshot_interval_sec"] = self.s_shot_interval.value()
        self.cfg["foreground_poll_sec"] = self.s_fg_poll.value()
        self.cfg["camera_index"] = self.s_cam_idx.value()
        self.cfg["covered_brightness_threshold"] = float(self.s_cover.value())
        self.cfg["retention_days"] = self.s_retention.value()
        self.cfg["screenshot_jpeg_quality"] = self.s_jpeg_q.value()
        self.cfg["screenshot_max_width"] = self.s_max_w.value()
        self.cfg["enable_telegram"] = self.s_telegram.isChecked()
        self.cfg["telegram_token"] = self.s_tg_token.text().strip()
        self.cfg["telegram_chat_id"] = self.s_tg_chat.text().strip()
        configmod.save_config(self.cfg)
        QMessageBox.information(self, "Saved", "Settings saved. Restart monitoring to apply.")

    # ---- refresh -------------------------------------------------------
    def _on_nav(self, row):
        self.pages.setCurrentIndex(row)
        self.refresh_current()

    def refresh_current(self):
        idx = self.pages.currentIndex()
        if idx == 0:
            self._load_events()
        elif idx == 1:
            self._load_usage()
        elif idx == 2:
            self._load_unlock()
        elif idx == 3:
            self._load_screens()

    def _load_events(self):
        rows = self.db.get_events()
        self.events_tbl.setRowCount(len(rows))
        for i, r in enumerate(rows):
            self.events_tbl.setItem(i, 0, QTableWidgetItem(r["ts"].replace("T", "  ")))
            self.events_tbl.setItem(i, 1, QTableWidgetItem(r["type"]))
            self.events_tbl.setItem(i, 2, QTableWidgetItem(r["details"] or ""))

    def _load_usage(self):
        summ = self.db.get_usage_summary()
        parts = [f"{r['app']}: {self._fmt(r['total'])}" for r in summ if r["app"]]
        self.summary_lbl.setText("Totals — " + ("   |   ".join(parts) if parts else "no data yet"))
        rows = self.db.get_usage()
        self.usage_tbl.setRowCount(len(rows))
        for i, r in enumerate(rows):
            self.usage_tbl.setItem(i, 0, QTableWidgetItem(r["app"] or ""))
            self.usage_tbl.setItem(i, 1, QTableWidgetItem(r["title"] or ""))
            self.usage_tbl.setItem(i, 2, QTableWidgetItem((r["start_ts"] or "").replace("T", "  ")))
            self.usage_tbl.setItem(i, 3, QTableWidgetItem((r["end_ts"] or "").replace("T", "  ")))
            self.usage_tbl.setItem(i, 4, QTableWidgetItem(self._fmt(r["seconds"])))

    def _load_unlock(self):
        rows = self.db.get_unlock_photos()
        items = []
        for r in rows:
            cap = r["ts"].replace("T", "  ")
            if r["covered"]:
                cap += "  — CAMERA COVERED"
            elif r["brightness"] is not None:
                cap += f"  (brightness {r['brightness']:.0f})"
            items.append((r["path"], cap, bool(r["covered"])))
        self.unlock_grid.set_items(items)

    def _load_screens(self):
        rows = self.db.get_screenshots()
        items = [(r["path"], f"{r['kind']}  {r['ts'].replace('T', '  ')}", False) for r in rows]
        self.screen_grid.set_items(items)

    @staticmethod
    def _fmt(seconds):
        seconds = int(seconds or 0)
        h, rem = divmod(seconds, 3600)
        m, s = divmod(rem, 60)
        if h:
            return f"{h}h {m}m"
        if m:
            return f"{m}m {s}s"
        return f"{s}s"

    def closeEvent(self, e):
        try:
            self.monitor.stop()
        except Exception:
            pass
        super().closeEvent(e)


def main():
    cfg = configmod.load_config()
    db = Database(os.path.join(cfg["data_dir"], "tracker.db"))
    app = QApplication(sys.argv)
    app.setStyleSheet(LIGHT_QSS)
    win = Dashboard(db, cfg)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

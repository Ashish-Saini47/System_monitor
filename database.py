"""SQLite storage for events, app usage, screenshots and unlock photos.

A single connection is shared across threads (check_same_thread=False) and all
writes are serialised through a lock, which is fine for this app's low volume.
"""
import sqlite3
import threading
from datetime import datetime


def now_iso():
    return datetime.now().isoformat(timespec="seconds")


class Database:
    def __init__(self, path):
        self.path = path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        with self._lock:
            c = self._conn.cursor()
            c.executescript(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts        TEXT NOT NULL,
                    type      TEXT NOT NULL,      -- monitor_start | monitor_stop | lock | unlock
                    details   TEXT
                );
                CREATE TABLE IF NOT EXISTS app_usage (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    app       TEXT,
                    title     TEXT,
                    start_ts  TEXT NOT NULL,
                    end_ts    TEXT NOT NULL,
                    seconds   INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS screenshots (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts        TEXT NOT NULL,
                    path      TEXT NOT NULL,
                    kind      TEXT NOT NULL        -- periodic | unlock
                );
                CREATE TABLE IF NOT EXISTS unlock_photos (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts        TEXT NOT NULL,
                    path      TEXT,
                    covered   INTEGER NOT NULL DEFAULT 0,
                    brightness REAL
                );
                """
            )
            self._conn.commit()

    # ---- writers -------------------------------------------------------
    def add_event(self, type_, details=""):
        with self._lock:
            self._conn.execute(
                "INSERT INTO events (ts, type, details) VALUES (?,?,?)",
                (now_iso(), type_, details),
            )
            self._conn.commit()

    def add_usage(self, app, title, start_ts, end_ts, seconds):
        with self._lock:
            self._conn.execute(
                "INSERT INTO app_usage (app, title, start_ts, end_ts, seconds) VALUES (?,?,?,?,?)",
                (app, title, start_ts, end_ts, int(seconds)),
            )
            self._conn.commit()

    def add_screenshot(self, path, kind):
        with self._lock:
            self._conn.execute(
                "INSERT INTO screenshots (ts, path, kind) VALUES (?,?,?)",
                (now_iso(), path, kind),
            )
            self._conn.commit()

    def add_unlock_photo(self, path, covered, brightness):
        with self._lock:
            self._conn.execute(
                "INSERT INTO unlock_photos (ts, path, covered, brightness) VALUES (?,?,?,?)",
                (now_iso(), path, 1 if covered else 0, brightness),
            )
            self._conn.commit()

    def purge_images_before(self, cutoff_iso):
        """Delete screenshot + unlock_photo rows older than cutoff. Returns the
        list of file paths that were removed, so the caller can unlink them."""
        with self._lock:
            paths = []
            for tbl in ("screenshots", "unlock_photos"):
                cur = self._conn.execute(
                    f"SELECT path FROM {tbl} WHERE ts < ?", (cutoff_iso,)
                )
                paths.extend(r["path"] for r in cur.fetchall())
                self._conn.execute(f"DELETE FROM {tbl} WHERE ts < ?", (cutoff_iso,))
            self._conn.commit()
            return [p for p in paths if p]

    # ---- readers -------------------------------------------------------
    def get_events(self, limit=500):
        cur = self._conn.execute(
            "SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)
        )
        return cur.fetchall()

    def get_usage(self, limit=500):
        cur = self._conn.execute(
            "SELECT * FROM app_usage ORDER BY id DESC LIMIT ?", (limit,)
        )
        return cur.fetchall()

    def get_usage_summary(self, limit=30):
        cur = self._conn.execute(
            "SELECT app, SUM(seconds) AS total FROM app_usage "
            "GROUP BY app ORDER BY total DESC LIMIT ?",
            (limit,),
        )
        return cur.fetchall()

    def get_screenshots(self, limit=300):
        cur = self._conn.execute(
            "SELECT * FROM screenshots ORDER BY id DESC LIMIT ?", (limit,)
        )
        return cur.fetchall()

    def get_unlock_photos(self, limit=300):
        cur = self._conn.execute(
            "SELECT * FROM unlock_photos ORDER BY id DESC LIMIT ?", (limit,)
        )
        return cur.fetchall()

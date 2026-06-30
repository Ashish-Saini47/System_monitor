# Laptop Activity Tracker (Windows)

A self-monitoring desktop app for **your own laptop**. It records who used the
machine and when, so you can spot activity during times you weren't using it.

## What it does

- **App / window usage** — which app was in the foreground and for how long, timestamped.
- **Lock / unlock events** — every time the workstation is locked or unlocked.
- **Webcam photo on every unlock** — a "who just got in" snapshot. If the camera
  is covered/blocked, the photo comes out near-black and the entry is **flagged
  "CAMERA COVERED"** (red) so you have a record either way.
- **Periodic screenshots** — at a configurable interval, skipped while locked. Saved as
  **downscaled JPEG** (default max width 1280px, quality 70) to keep them small.
- **PySide6 dashboard** — review everything: activity log, usage table with totals,
  unlock-photo gallery, screenshot gallery, and settings.

All data is stored locally: `data/tracker.db` (SQLite) plus image files under
`data/screenshots` and `data/unlock_photos`. Nothing leaves the machine.

## About the "block login if the camera is covered" idea

That isn't included, on purpose. The Windows login screen runs *before* your user
session (handled by Winlogon), so no normal app — Python or otherwise — can reject
a **correct** password based on camera state. Doing that would mean writing a custom
Windows Credential Provider in C++/COM, and it would lock *you* out whenever your own
shutter was closed, while still being bypassable by anyone technical. So instead of
blocking, the app **captures and flags** every covered-camera unlock. You get the
evidence without the self-lockout.

## Setup

```bash
pip install -r requirements.txt
python app.py
```

Requires Python 3.10+ on Windows 10/11. A working webcam is needed for unlock photos
(the rest works without one).

## Usage

1. Launch `python app.py`.
2. Click **Start Monitoring**. Leave the window open or minimised — the background
   threads keep running while the app is open.
3. Check the tabs to review captured data. **Settings** lets you toggle features and
   change intervals (apply on next Start).

## Run it automatically at login (optional)

Use Task Scheduler so it starts with Windows:

1. Open **Task Scheduler** → **Create Task**.
2. *General*: name it, check **Run only when user is logged on**.
3. *Triggers*: New → **At log on**.
4. *Actions*: New → Program/script `pythonw.exe`, arguments the full path to `app.py`,
   "Start in" the project folder.
5. Save. (Use `pythonw.exe` instead of `python.exe` to avoid a console window.)

## Telegram notification on every unlock

Get a message (with the unlock photo attached) every time the laptop is unlocked.

1. In Telegram, message **@BotFather** → `/newbot` → follow prompts → copy the **bot token**.
2. Send any message to your new bot, then get your **chat id**: open
   `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` in a browser and read the
   `chat.id` value (or message **@userinfobot**, which replies with your id).
3. In the app: **Settings** → tick *Send Telegram notification on every unlock*,
   paste the token and chat id → **Send test message** to confirm → **Save settings**.
4. Restart monitoring. From then on, each unlock sends the photo + timestamp; if the
   camera was covered, you get a "CAMERA COVERED" alert instead.

The token field is masked, and the token/chat id are stored in `config.json` on your
machine — keep that file private.

## Storage & retention

- Screenshots are saved as **downscaled JPEG**, which is roughly 5–10× smaller than the
  old full-size PNGs. Tune **max width** and **JPEG quality** in Settings.
- A **retention** setting (default **7 days**) auto-deletes screenshots and unlock photos
  older than the window — both the files and their database rows. Set it to **0** to keep
  everything forever. Cleanup runs at startup and every ~6 hours while monitoring.
- Retention applies to **images only**. The text logs (events, app usage) are tiny and
  kept indefinitely, so your forensic history isn't lost when old screenshots are pruned.

## Notes & limits

- Detects lock/unlock by watching the Windows input-desktop switch — no admin rights needed.
- Works for a **single shared user account** (the usual home-laptop case). It can't see
  unlock photos for a *different* Windows user account, since each account is a separate session.
- Tune the **covered-camera threshold** in Settings if your room is dark and normal
  photos get falsely flagged as covered, or vice-versa.
- Built to run **openly on a device you own**. Don't deploy it covertly on someone
  else's machine.

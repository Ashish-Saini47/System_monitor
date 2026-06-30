"""Capture helpers: webcam photo (with covered-camera detection) and screenshots.

All imports of the heavier libs are done lazily so the GUI still launches even
if a library is missing on the target machine; the relevant feature just logs a
warning and is skipped.
"""
import os
from datetime import datetime


def _stamp():
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def capture_screenshot(data_dir, kind="periodic", max_width=1280, quality=70):
    """Grab the primary monitor, downscale, save as JPEG. Returns path or None.

    Falls back to full-size PNG only if OpenCV/numpy aren't available.
    """
    try:
        import mss
        import mss.tools
    except Exception as e:
        print(f"[capture] screenshot unavailable: {e}")
        return None

    out_dir = os.path.join(data_dir, "screenshots")
    os.makedirs(out_dir, exist_ok=True)
    base = os.path.join(out_dir, f"{kind}_{_stamp()}")
    try:
        with mss.mss() as sct:
            mon = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
            img = sct.grab(mon)
            try:
                import numpy as np
                import cv2
                frame = np.array(img)  # BGRA
                frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                h, w = frame.shape[:2]
                if max_width and w > max_width:
                    scale = float(max_width) / w
                    frame = cv2.resize(
                        frame, (int(w * scale), int(h * scale)),
                        interpolation=cv2.INTER_AREA,
                    )
                path = base + ".jpg"
                cv2.imwrite(path, frame, [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)])
                return path
            except Exception as e:
                # fallback: full-size PNG
                print(f"[capture] JPEG path failed ({e}); saving PNG")
                path = base + ".png"
                mss.tools.to_png(img.rgb, img.size, output=path)
                return path
    except Exception as e:
        print(f"[capture] screenshot failed: {e}")
        return None


def capture_webcam(data_dir, camera_index=0, covered_threshold=12.0, warmup_frames=5):
    """Grab one webcam frame.

    Returns (path, brightness, covered):
      path       -> saved JPG path or None on failure
      brightness -> mean grayscale 0..255 (None if not captured)
      covered    -> True if the frame is near-black (lens covered / shutter closed)
    """
    try:
        import cv2
    except Exception as e:
        print(f"[capture] webcam unavailable: {e}")
        return None, None, False

    out_dir = os.path.join(data_dir, "unlock_photos")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"unlock_{_stamp()}.jpg")

    cap = None
    try:
        # CAP_DSHOW tends to open faster/more reliably on Windows.
        backend = getattr(cv2, "CAP_DSHOW", 0)
        cap = cv2.VideoCapture(camera_index, backend)
        if not cap.isOpened():
            cap = cv2.VideoCapture(camera_index)
        if not cap.isOpened():
            print("[capture] could not open webcam")
            return None, None, False

        frame = None
        for _ in range(max(1, warmup_frames)):  # let exposure settle
            ok, f = cap.read()
            if ok and f is not None:
                frame = f
        if frame is None:
            print("[capture] no frame from webcam")
            return None, None, False

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        brightness = float(gray.mean())
        covered = brightness < float(covered_threshold)
        cv2.imwrite(path, frame)
        return path, brightness, covered
    except Exception as e:
        print(f"[capture] webcam failed: {e}")
        return None, None, False
    finally:
        if cap is not None:
            cap.release()

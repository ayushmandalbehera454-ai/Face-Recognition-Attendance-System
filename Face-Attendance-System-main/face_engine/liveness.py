"""Basic anti-spoofing: the person must BLINK (eyes open -> closed -> open).

A still photo or a printed picture cannot blink. This reduces casual photo
impersonation but is NOT bullet-proof (a video replay can fool it). For high-security
use, combine with a human check, which this project supports through manual review.
"""
import threading
import time
import numpy as np

EAR_CLOSED = 0.21
EAR_OPEN = 0.25
WINDOW_SECONDS = 8.0


def eye_aspect_ratio(eye_points):
    """eye_points: 6 (x, y) landmarks of one eye (dlib order)."""
    p = np.asarray(eye_points, dtype=float)
    v1 = np.linalg.norm(p[1] - p[5])
    v2 = np.linalg.norm(p[2] - p[4])
    h = np.linalg.norm(p[0] - p[3])
    return float((v1 + v2) / (2.0 * h)) if h else 0.0


def ear_from_landmarks(landmarks):
    """Average EAR of both eyes from a face_recognition landmarks dict."""
    try:
        return (eye_aspect_ratio(landmarks["left_eye"]) +
                eye_aspect_ratio(landmarks["right_eye"])) / 2.0
    except (KeyError, IndexError, ValueError):
        return None


class LivenessTracker:
    """Remembers recent eye states per person and reports when a blink completed."""

    def __init__(self, window=WINDOW_SECONDS):
        self.window = window
        self._hist = {}
        self._lock = threading.Lock()

    def update(self, key, ear, now=None):
        if ear is None:
            return False
        now = time.monotonic() if now is None else now
        with self._lock:
            hist = self._hist.setdefault(key, [])
            hist.append((now, ear))
            hist[:] = [(t, e) for (t, e) in hist if now - t <= self.window]
            state = 0  # 0 want open, 1 saw open, 2 saw closed
            for _, e in hist:
                if state == 0 and e >= EAR_OPEN:
                    state = 1
                elif state == 1 and e <= EAR_CLOSED:
                    state = 2
                elif state == 2 and e >= EAR_OPEN:
                    self._hist.pop(key, None)  # reset so each check-in needs a new blink
                    return True
        return False

    def reset(self, key=None):
        with self._lock:
            if key is None:
                self._hist.clear()
            else:
                self._hist.pop(key, None)


tracker = LivenessTracker()

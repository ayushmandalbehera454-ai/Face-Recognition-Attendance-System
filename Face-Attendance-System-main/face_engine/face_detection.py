"""Decode webcam frames and find faces in them."""
import base64
import cv2
import numpy as np

MAX_WIDTH = 640  # frames wider than this are shrunk (faster, still accurate)


def _fr():
    import face_recognition  # imported lazily so the web app starts even if dlib is missing
    return face_recognition


def decode_image(data_url):
    """'data:image/jpeg;base64,....' -> RGB numpy array, or None if invalid."""
    if not data_url or not isinstance(data_url, str):
        return None
    try:
        payload = data_url.split(",", 1)[1] if "," in data_url else data_url
        raw = base64.b64decode(payload, validate=False)
        arr = np.frombuffer(raw, dtype=np.uint8)
        bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if bgr is None:
            return None
        h, w = bgr.shape[:2]
        if w > MAX_WIDTH:
            scale = MAX_WIDTH / w
            bgr = cv2.resize(bgr, (MAX_WIDTH, int(h * scale)), interpolation=cv2.INTER_AREA)
        return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    except Exception:
        return None


def detect_faces(rgb):
    """Return face boxes as (top, right, bottom, left) tuples. HOG model = fast on CPU."""
    return _fr().face_locations(rgb, number_of_times_to_upsample=1, model="hog")

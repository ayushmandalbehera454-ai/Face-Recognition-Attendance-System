"""Compare detected faces with stored (decrypted) embeddings."""
import threading
import numpy as np
from flask import current_app

from extensions import db
from face_engine import face_detection, face_encoding
from face_engine.liveness import ear_from_landmarks


def _fr():
    import face_recognition
    return face_recognition


# ---------------------------------------------------------------- embedding cache
class EmbeddingStore:
    """Keeps all decrypted embeddings in RAM so every frame is matched quickly."""

    def __init__(self):
        self._lock = threading.Lock()
        self._ids = None      # list of student primary keys, one per vector
        self._matrix = None   # N x 128 array

    def invalidate(self):
        with self._lock:
            self._ids, self._matrix = None, None

    def get(self):
        with self._lock:
            if self._ids is None:
                self._load()
            return self._ids, self._matrix

    def _load(self):
        from models.student import FaceEmbedding, Student
        rows = (db.session.query(FaceEmbedding.student_id, FaceEmbedding.encrypted_vector)
                .join(Student, Student.id == FaceEmbedding.student_id)
                .filter(Student.active.is_(True)).all())
        ids, vecs = [], []
        for sid, blob in rows:
            try:
                vecs.append(face_encoding.decrypt_vector(blob))
                ids.append(sid)
            except Exception:
                continue  # wrong key or corrupted row: skip, never crash the camera
        self._ids = ids
        self._matrix = np.vstack(vecs) if vecs else np.empty((0, 128))


store = EmbeddingStore()


# ---------------------------------------------------------------- matching maths
def confidence_from_distance(distance, threshold=0.5):
    """Map a distance to a 0-100 score (standard face_recognition formula)."""
    if distance > threshold:
        return round(max(0.0, (1.0 - distance) / ((1.0 - threshold) * 2.0)) * 100, 1)
    lin = (1.0 - distance) / ((1.0 - threshold) * 2.0)
    return round((lin + ((1.0 - lin) * ((lin - 0.5) * 2.0) ** 0.2)) * 100, 1)


def decide_match(encoding, ids, matrix, threshold, margin):
    """Return (state, student_pk, distance).  state: matched | ambiguous | unknown."""
    if matrix is None or len(matrix) == 0:
        return "unknown", None, None
    dist = np.linalg.norm(matrix - encoding, axis=1)  # same as face_recognition.face_distance
    order = np.argsort(dist)
    best = int(order[0])
    best_d, best_id = float(dist[best]), ids[best]
    if best_d > threshold:
        return "unknown", None, best_d
    for j in order[1:]:
        if ids[int(j)] != best_id:  # nearest vector that belongs to someone else
            second = float(dist[int(j)])
            if second <= threshold and (second - best_d) < margin:
                return "ambiguous", None, best_d
            break
    return "matched", best_id, best_d


def identify_faces(rgb, with_liveness=True):
    """Detect + recognise every face in a frame. Boxes are normalised to 0-1."""
    fr = _fr()
    h, w = rgb.shape[:2]
    locations = face_detection.detect_faces(rgb)
    if not locations:
        return []
    encodings = face_encoding.encode_faces(rgb, locations)
    landmarks = fr.face_landmarks(rgb, locations) if with_liveness else [None] * len(locations)
    ids, matrix = store.get()
    cfg = current_app.config

    results = []
    for loc, enc, lm in zip(locations, encodings, landmarks):
        top, right, bottom, left = loc
        state, pk, dist = decide_match(enc, ids, matrix, cfg["MATCH_THRESHOLD"], cfg["AMBIGUITY_MARGIN"])
        results.append({
            "box": {"x": left / w, "y": top / h, "w": (right - left) / w, "h": (bottom - top) / h},
            "state": state,
            "student_pk": pk,
            "distance": None if dist is None else round(dist, 3),
            "confidence": 0.0 if dist is None else confidence_from_distance(dist, cfg["MATCH_THRESHOLD"]),
            "ear": ear_from_landmarks(lm) if lm else None,
        })
    return results

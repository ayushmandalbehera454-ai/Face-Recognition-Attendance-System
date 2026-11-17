"""Turn faces into 128-number embeddings and protect them at rest (Fernet encryption)."""
import os
import numpy as np
from cryptography.fernet import Fernet
from flask import current_app

_fernet_cache = {}


def _fr():
    import face_recognition
    return face_recognition


def _get_fernet():
    key = current_app.config.get("EMBEDDING_KEY", "").strip()
    if not key:
        # No key configured: create one once and keep it next to the database.
        path = os.path.join(current_app.config["DATABASE_FOLDER"], "embedding.key")
        if os.path.exists(path):
            key = open(path, "r").read().strip()
        else:
            key = Fernet.generate_key().decode()
            with open(path, "w") as f:
                f.write(key)
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
    if key not in _fernet_cache:
        _fernet_cache[key] = Fernet(key.encode())
    return _fernet_cache[key]


def encode_faces(rgb, locations):
    """List of 128-d float64 vectors, one per face location."""
    return _fr().face_encodings(rgb, known_face_locations=locations, num_jitters=1)


def encrypt_vector(vec):
    return _get_fernet().encrypt(np.asarray(vec, dtype=np.float64).tobytes())


def decrypt_vector(blob):
    return np.frombuffer(_get_fernet().decrypt(bytes(blob)), dtype=np.float64)

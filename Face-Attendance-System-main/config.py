import os
from datetime import timedelta
from dotenv import load_dotenv

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))


def _bool(name, default="true"):
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")


def _db_uri():
    url = os.environ.get("DATABASE_URL", "sqlite:///database/attendance.db")
    # Relative sqlite paths become absolute so it works from any folder
    if url.startswith("sqlite:///") and not url.startswith("sqlite:////") and ":memory:" not in url:
        url = "sqlite:///" + os.path.join(BASE_DIR, url.replace("sqlite:///", "", 1))
    return url


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-me")
    SQLALCHEMY_DATABASE_URI = _db_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    WTF_CSRF_TIME_LIMIT = None
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024

    DATASET_FOLDER = os.path.join(BASE_DIR, "dataset")
    EXPORT_FOLDER = os.path.join(BASE_DIR, "exports")
    DATABASE_FOLDER = os.path.join(BASE_DIR, "database")

    # Face recognition
    EMBEDDING_KEY = os.environ.get("EMBEDDING_KEY", "")
    MATCH_THRESHOLD = float(os.environ.get("MATCH_THRESHOLD", 0.50))  # lower = stricter
    AMBIGUITY_MARGIN = 0.04       # two different people this close => needs manual review
    MIN_ENROLL_IMAGES = 3
    LIVENESS_REQUIRED = _bool("LIVENESS_REQUIRED", "true")
    SAVE_FACE_IMAGES = False      # keep raw photos on disk? default: only encrypted embeddings

    # Attendance rule
    LATE_AFTER = os.environ.get("LATE_AFTER", "09:15")

    # First-run admin
    ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Admin@12345")
    ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@example.com")


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    WTF_CSRF_ENABLED = False
    LIVENESS_REQUIRED = False


config_by_name = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
}

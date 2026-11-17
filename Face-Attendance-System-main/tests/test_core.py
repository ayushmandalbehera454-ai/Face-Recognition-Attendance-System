from datetime import date

import numpy as np

from extensions import db
from models.admin import Admin
from models.attendance import Attendance
from models.student import Student, Department
from services import attendance_service as svc
from face_engine.liveness import LivenessTracker
from face_engine.recognition import decide_match, confidence_from_distance


def make_student(code="S001", name="Asha Rao", email="asha@example.com"):
    s = Student(student_code=code, name=name, email=email)
    db.session.add(s)
    db.session.commit()
    return s


# ---------------------------------------------------------------- web / auth
def test_health(client):
    assert client.get("/health").get_json() == {"status": "ok"}


def test_dashboard_requires_login(client):
    r = client.get("/dashboard")
    assert r.status_code == 302 and "/login" in r.headers["Location"]


def test_api_requires_login_returns_json(client):
    r = client.get("/api/dashboard/stats")
    assert r.status_code == 401


def test_login_and_logout(app, client):
    bad = client.post("/login", data={"username": "admin", "password": "nope"})
    assert b"Wrong username or password" in bad.data
    r = client.post("/login", data={"username": app.config["ADMIN_USERNAME"], "password": app.config["ADMIN_PASSWORD"]})
    assert r.status_code == 302
    assert client.get("/dashboard").status_code == 200
    assert client.post("/logout").status_code == 302
    assert client.get("/dashboard").status_code == 302


def test_password_is_hashed(app):
    with app.app_context():
        admin = Admin.query.first()
        assert admin.password_hash != app.config["ADMIN_PASSWORD"]
        assert admin.check_password(app.config["ADMIN_PASSWORD"])


def test_viewer_cannot_change_data(app, admin_client):
    with app.app_context():
        v = Admin(username="viewer", email="v@example.com", role="viewer")
        v.set_password("Viewer123")
        db.session.add(v)
        db.session.commit()
    admin_client.post("/logout")
    admin_client.post("/login", data={"username": "viewer", "password": "Viewer123"})
    r = admin_client.post("/api/students", json={"name": "Test User", "student_code": "T1", "email": "t@example.com"})
    assert r.status_code == 403


# ---------------------------------------------------------------- students
def test_register_without_consent_is_manual_only(app, admin_client):
    r = admin_client.post("/api/students", json={"name": "Ravi Kumar", "student_code": "E100",
                                                 "email": "ravi@example.com", "consent": False})
    assert r.status_code == 201
    with app.app_context():
        s = Student.query.filter_by(student_code="E100").first()
        assert s is not None and not s.has_face_data and not s.consent_given


def test_registration_validation(admin_client):
    r = admin_client.post("/api/students", json={"name": "X", "student_code": "!!", "email": "bad"})
    assert r.status_code == 400


def test_duplicate_id_rejected(app, admin_client):
    body = {"name": "Meena Das", "student_code": "D1", "email": "m@example.com"}
    assert admin_client.post("/api/students", json=body).status_code == 201
    body["email"] = "other@example.com"
    assert admin_client.post("/api/students", json=body).status_code == 400


def test_department_crud(app, admin_client):
    admin_client.post("/departments", data={"name": "Physics"})
    with app.app_context():
        assert Department.query.filter_by(name="Physics").count() == 1


# ---------------------------------------------------------------- attendance
def test_one_record_per_day_and_manual_correction(app, admin_client):
    with app.app_context():
        s = make_student()
        rec, created = svc.mark_attendance(s)
        assert created
        rec2, created2 = svc.mark_attendance(s)
        assert not created2 and rec2.id == rec.id
        sid = s.id
    r = admin_client.post("/api/attendance/manual", json={"student_id": sid, "status": "Late", "note": "Bus delay"})
    assert r.status_code == 200
    with app.app_context():
        rows = Attendance.query.filter_by(student_id=sid, date=date.today()).all()
        assert len(rows) == 1 and rows[0].status == "Late" and rows[0].method == "manual"


def test_future_manual_date_rejected(app, admin_client):
    with app.app_context():
        sid = make_student().id
    r = admin_client.post("/api/attendance/manual", json={"student_id": sid, "status": "Present", "date": "2999-01-01"})
    assert r.status_code == 400


def test_recognition_marks_once_and_unknown_not_penalised(app):
    with app.app_context():
        s = make_student()
        box = {"x": .1, "y": .1, "w": .2, "h": .2}
        face = {"box": box, "state": "matched", "student_pk": s.id, "distance": 0.3, "confidence": 88.0, "ear": None}
        first = svc.process_recognition([face])[0]
        second = svc.process_recognition([face])[0]
        assert first["state"] == "marked" and second["state"] == "already"
        assert Attendance.query.filter_by(student_id=s.id).count() == 1
        unknown = svc.process_recognition([{"box": box, "state": "unknown", "student_pk": None,
                                            "distance": 0.9, "confidence": 0, "ear": None}])[0]
        assert unknown["name"] == "Unregistered"
        assert Attendance.query.count() == 1  # nothing written for the unknown face


def test_dashboard_stats(app, admin_client):
    with app.app_context():
        s = make_student()
        svc.mark_attendance(s)
    d = admin_client.get("/api/dashboard/stats").get_json()
    assert d["today"]["total"] == 1 and d["today"]["attended"] == 1 and d["today"]["percentage"] == 100.0
    assert len(d["daily"]["values"]) == 7


# ---------------------------------------------------------------- reports
def test_report_exports(app, admin_client):
    with app.app_context():
        svc.mark_attendance(make_student())
    for kind in ("daily", "monthly", "department"):
        assert admin_client.get(f"/api/reports/data?type={kind}").status_code == 200
    csv = admin_client.get("/reports/export/csv?type=daily")
    xlsx = admin_client.get("/reports/export/xlsx?type=daily")
    pdf = admin_client.get("/reports/export/pdf?type=daily")
    assert csv.status_code == 200 and b"Student ID" in csv.data
    assert xlsx.data[:2] == b"PK"
    assert pdf.data[:4] == b"%PDF"


def test_individual_report_needs_student(admin_client):
    assert admin_client.get("/api/reports/data?type=individual").status_code == 400


# ---------------------------------------------------------------- face maths (no camera needed)
def test_decide_match_states():
    ids = [1, 1, 2]
    matrix = np.array([[0.0] * 128, [0.01] * 128, [1.0] * 128])
    assert decide_match(np.zeros(128), ids, matrix, 0.5, 0.04)[:2] == ("matched", 1)
    assert decide_match(np.full(128, 5.0), ids, matrix, 0.5, 0.04)[0] == "unknown"
    # a face exactly between two different people must go to manual review
    close = np.array([[0.0] * 128, [0.0] * 128])
    close[1][0] = 0.02
    assert decide_match(np.zeros(128), [1, 2], close, 0.5, 0.04)[0] == "ambiguous"
    assert decide_match(np.zeros(128), [], np.empty((0, 128)), 0.5, 0.04)[0] == "unknown"


def test_confidence_scale():
    assert confidence_from_distance(0.0) > 95
    assert confidence_from_distance(0.9) <= 10


def test_blink_detection():
    t = LivenessTracker()
    assert not t.update("a", 0.30, now=0.0)
    assert not t.update("a", 0.30, now=0.2)      # eyes open only: a photo never blinks
    assert not t.update("a", 0.15, now=0.4)      # closed
    assert t.update("a", 0.30, now=0.6)          # open again -> blink completed
    assert not t.update("a", 0.30, now=0.8)      # needs a fresh blink next time

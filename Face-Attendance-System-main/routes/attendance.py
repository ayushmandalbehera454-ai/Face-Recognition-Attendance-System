from datetime import date, datetime

from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user

from extensions import db
from models.attendance import Attendance, STATUSES
from models.student import Student, Department
from face_engine import face_detection, recognition
from services import attendance_service as svc
from utils import roles_required, log_activity, WRITE_ROLES

bp = Blueprint("attendance", __name__)


@bp.route("/attendance")
@login_required
def attendance_page():
    return render_template("attendance.html",
                           departments=Department.query.order_by(Department.name).all(),
                           students=Student.query.filter_by(active=True).order_by(Student.name).all(),
                           statuses=STATUSES, today=date.today().isoformat())


@bp.route("/api/attendance/recognize", methods=["POST"])
@login_required
def recognize():
    data = request.get_json(silent=True) or {}
    rgb = face_detection.decode_image(data.get("image"))
    if rgb is None:
        return jsonify(error="Could not read the camera frame."), 400
    try:
        faces = recognition.identify_faces(rgb, with_liveness=True)
    except ImportError:
        return jsonify(error="face_recognition / dlib is not installed on the server."), 500
    results = svc.process_recognition(faces, admin_id=current_user.id)
    return jsonify(faces=results)


@bp.route("/api/attendance/list")
@login_required
def list_records():
    def parse(v):
        return datetime.strptime(v, "%Y-%m-%d").date() if v else None
    try:
        rows = svc.query_records(parse(request.args.get("from")), parse(request.args.get("to")),
                                 request.args.get("department", type=int), request.args.get("status") or None,
                                 (request.args.get("q") or "").strip() or None)
    except ValueError:
        return jsonify(error="Dates must look like 2026-01-31."), 400
    return jsonify(records=[svc.record_to_dict(*r) for r in rows])


@bp.route("/api/attendance/recent")
@login_required
def recent():
    """Used by the notification bell: new records since id `after`."""
    after = request.args.get("after", type=int)
    last = db.session.query(db.func.max(Attendance.id)).scalar() or 0
    if after is None:
        return jsonify(last_id=last, records=[])
    rows = (db.session.query(Attendance, Student).join(Student, Student.id == Attendance.student_id)
            .filter(Attendance.id > after).order_by(Attendance.id).limit(10).all())
    return jsonify(last_id=last, records=[
        {"id": a.id, "name": s.name, "status": a.status, "time": a.time.strftime("%H:%M"), "method": a.method}
        for a, s in rows])


@bp.route("/api/attendance/manual", methods=["POST"])
@roles_required(*WRITE_ROLES)
def manual():
    """Authorised manual mark / correction. Overwrites that day's record (kept in the activity log)."""
    data = request.get_json(silent=True) or {}
    try:
        student = db.session.get(Student, int(data.get("student_id") or 0))
    except (TypeError, ValueError):
        student = None
    status = data.get("status")
    if not student or status not in STATUSES:
        return jsonify(error="Choose a student and a valid status."), 400
    try:
        day = datetime.strptime(data.get("date") or date.today().isoformat(), "%Y-%m-%d").date()
    except ValueError:
        return jsonify(error="Invalid date."), 400
    if day > date.today():
        return jsonify(error="You cannot mark attendance for a future date."), 400
    note = (data.get("note") or "").strip()[:200] or "Manual entry"
    when = datetime.combine(day, datetime.now().time()) if day != date.today() else datetime.now()
    existing = Attendance.query.filter_by(student_id=student.id, date=day).first()
    before = existing.status if existing else "none"
    svc.mark_attendance(student, status=status, method="manual", note=note,
                        admin_id=current_user.id, when=when, overwrite=True)
    log_activity("attendance_manual", f"{student.student_code} {day}: {before} -> {status} ({note})")
    db.session.commit()
    return jsonify(ok=True, message=f"{student.name} marked {status} for {day}.")


@bp.route("/api/attendance/<int:rid>", methods=["DELETE"])
@roles_required(*WRITE_ROLES)
def delete_record(rid):
    rec = db.get_or_404(Attendance, rid)
    log_activity("attendance_deleted", f"record {rid} student {rec.student_id} {rec.date}")
    db.session.delete(rec)
    db.session.commit()
    return jsonify(ok=True)

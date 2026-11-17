from datetime import datetime

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_required

from extensions import db
from models.student import Student, Department, FaceEmbedding
from face_engine import face_detection, face_encoding
from face_engine.recognition import store
from utils import roles_required, log_activity, ID_RE, EMAIL_RE, NAME_RE, WRITE_ROLES

bp = Blueprint("students", __name__)


def _validate(name, code, email, student_id=None):
    errors = []
    if not NAME_RE.match(name or ""):
        errors.append("Name must be 2-80 letters (spaces, . ' - allowed).")
    if not ID_RE.match(code or ""):
        errors.append("ID must be 2-30 characters: letters, numbers, _ or -.")
    if not EMAIL_RE.match(email or ""):
        errors.append("Enter a valid email address.")
    q = Student.query
    if student_id:
        q = q.filter(Student.id != student_id)
    if code and q.filter(db.func.lower(Student.student_code) == code.lower()).first():
        errors.append("This ID is already registered.")
    if email and q.filter(db.func.lower(Student.email) == email.lower()).first():
        errors.append("This email is already registered.")
    return errors


# ------------------------------------------------------------------ pages
@bp.route("/students")
@login_required
def students():
    q = (request.args.get("q") or "").strip()
    dept = request.args.get("department", type=int)
    page = request.args.get("page", 1, type=int)
    query = Student.query
    if q:
        like = f"%{q}%"
        query = query.filter(db.or_(Student.name.ilike(like), Student.student_code.ilike(like), Student.email.ilike(like)))
    if dept:
        query = query.filter_by(department_id=dept)
    pagination = query.order_by(Student.name).paginate(page=page, per_page=12, error_out=False)
    return render_template("students.html", pagination=pagination, q=q, dept=dept,
                           departments=Department.query.order_by(Department.name).all())


@bp.route("/students/register")
@roles_required(*WRITE_ROLES)
def register_page():
    return render_template("registration.html", departments=Department.query.order_by(Department.name).all(),
                           min_images=current_app.config["MIN_ENROLL_IMAGES"])


@bp.route("/students/<int:sid>/edit", methods=["GET", "POST"])
@roles_required(*WRITE_ROLES)
def edit(sid):
    student = db.get_or_404(Student, sid)
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        code = (request.form.get("student_code") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        errors = _validate(name, code, email, student.id)
        if errors:
            for e in errors:
                flash(e, "danger")
        else:
            student.name, student.student_code, student.email = name, code, email
            student.department_id = request.form.get("department_id", type=int) or None
            student.active = request.form.get("active") == "on"
            log_activity("student_edited", f"{code} updated")
            db.session.commit()
            store.invalidate()
            flash("Profile saved.", "success")
            return redirect(url_for("students.students"))
    return render_template("student_edit.html", s=student, departments=Department.query.order_by(Department.name).all(),
                           min_images=current_app.config["MIN_ENROLL_IMAGES"])


@bp.route("/students/<int:sid>/delete", methods=["POST"])
@roles_required(*WRITE_ROLES)
def delete(sid):
    student = db.get_or_404(Student, sid)
    log_activity("student_deleted", f"{student.student_code} {student.name} deleted with all face data")
    db.session.delete(student)
    db.session.commit()
    store.invalidate()
    flash("Student and all their face data were deleted.", "success")
    return redirect(url_for("students.students"))


@bp.route("/students/<int:sid>/withdraw-consent", methods=["POST"])
@roles_required(*WRITE_ROLES)
def withdraw_consent(sid):
    student = db.get_or_404(Student, sid)
    FaceEmbedding.query.filter_by(student_id=student.id).delete()
    student.consent_given, student.consent_at = False, None
    log_activity("consent_withdrawn", f"{student.student_code}: face data erased")
    db.session.commit()
    store.invalidate()
    flash("Face data erased. This person can now only be marked manually.", "success")
    return redirect(url_for("students.edit", sid=sid))


# ------------------------------------------------------------------ departments
@bp.route("/departments", methods=["GET", "POST"])
@login_required
def departments():
    if request.method == "POST":
        from flask_login import current_user
        if not current_user.can_write:
            flash("You do not have permission to do this.", "danger")
            return redirect(url_for("students.departments"))
        name = (request.form.get("name") or "").strip()
        if not (2 <= len(name) <= 80):
            flash("Department name must be 2-80 characters.", "danger")
        elif Department.query.filter(db.func.lower(Department.name) == name.lower()).first():
            flash("That department already exists.", "danger")
        else:
            db.session.add(Department(name=name))
            log_activity("department_added", name)
            db.session.commit()
            flash("Department added.", "success")
        return redirect(url_for("students.departments"))
    return render_template("departments.html", departments=Department.query.order_by(Department.name).all())


@bp.route("/departments/<int:did>/delete", methods=["POST"])
@roles_required(*WRITE_ROLES)
def delete_department(did):
    dept = db.get_or_404(Department, did)
    if dept.students:
        flash("Move or delete the students in this department first.", "danger")
    else:
        log_activity("department_deleted", dept.name)
        db.session.delete(dept)
        db.session.commit()
        flash("Department deleted.", "success")
    return redirect(url_for("students.departments"))


# ------------------------------------------------------------------ enrolment API
def _encode_images(images):
    """Return (vectors, problems). Each image must contain exactly one face."""
    vectors, problems = [], 0
    for img in images[:15]:
        rgb = face_detection.decode_image(img)
        if rgb is None:
            problems += 1
            continue
        locs = face_detection.detect_faces(rgb)
        if len(locs) != 1:
            problems += 1
            continue
        vectors.append(face_encoding.encode_faces(rgb, locs)[0])
    return vectors, problems


def _find_duplicate_person(vectors, ignore_student_id=None):
    """Return the name of an already-registered person whose face matches the new one."""
    import numpy as np
    from models.student import Student as S
    ids, matrix = store.get()
    if matrix is None or len(matrix) == 0:
        return None
    threshold = current_app.config["MATCH_THRESHOLD"] - 0.05
    for v in vectors:
        dist = np.linalg.norm(matrix - v, axis=1)
        j = int(dist.argmin())
        if dist[j] <= threshold and ids[j] != ignore_student_id:
            return db.session.get(S, ids[j]).name
    return None


@bp.route("/api/students", methods=["POST"])
@roles_required(*WRITE_ROLES)
def api_create():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    code = (data.get("student_code") or "").strip()
    email = (data.get("email") or "").strip().lower()
    consent = bool(data.get("consent"))
    images = data.get("images") or []
    errors = _validate(name, code, email)
    if errors:
        return jsonify(error=" ".join(errors)), 400

    vectors = []
    if consent:
        minimum = current_app.config["MIN_ENROLL_IMAGES"]
        vectors, problems = _encode_images(images)
        if len(vectors) < minimum:
            return jsonify(error=f"Only {len(vectors)} usable photos. Need {minimum}+ photos with exactly one clear face. "
                                 "Face the camera in good light and retake.") , 400
        twin = _find_duplicate_person(vectors)
        if twin:
            return jsonify(error=f"This face already matches registered person '{twin}'."), 409

    student = Student(student_code=code, name=name, email=email,
                      department_id=int(data["department_id"]) if data.get("department_id") else None,
                      consent_given=consent, consent_at=datetime.utcnow() if consent else None)
    db.session.add(student)
    db.session.flush()
    for v in vectors:
        db.session.add(FaceEmbedding(student_id=student.id, encrypted_vector=face_encoding.encrypt_vector(v)))
    log_activity("student_registered", f"{code} {name} ({'face' if vectors else 'manual-only, no consent'})")
    db.session.commit()
    store.invalidate()
    return jsonify(ok=True, message=f"{name} registered" + (f" with {len(vectors)} face samples." if vectors else " (manual attendance only)."),
                   redirect=url_for("students.students")), 201


@bp.route("/api/students/<int:sid>/faces", methods=["POST"])
@roles_required(*WRITE_ROLES)
def api_recapture(sid):
    student = db.get_or_404(Student, sid)
    data = request.get_json(silent=True) or {}
    if not data.get("consent"):
        return jsonify(error="Consent is required to store face data."), 400
    minimum = current_app.config["MIN_ENROLL_IMAGES"]
    vectors, _ = _encode_images(data.get("images") or [])
    if len(vectors) < minimum:
        return jsonify(error=f"Only {len(vectors)} usable photos. Need {minimum}+ with exactly one clear face."), 400
    twin = _find_duplicate_person(vectors, ignore_student_id=student.id)
    if twin:
        return jsonify(error=f"This face already matches registered person '{twin}'."), 409
    FaceEmbedding.query.filter_by(student_id=student.id).delete()
    for v in vectors:
        db.session.add(FaceEmbedding(student_id=student.id, encrypted_vector=face_encoding.encrypt_vector(v)))
    student.consent_given = True
    student.consent_at = student.consent_at or datetime.utcnow()
    log_activity("faces_recaptured", student.student_code)
    db.session.commit()
    store.invalidate()
    return jsonify(ok=True, message=f"Saved {len(vectors)} new face samples.", redirect=url_for("students.students"))

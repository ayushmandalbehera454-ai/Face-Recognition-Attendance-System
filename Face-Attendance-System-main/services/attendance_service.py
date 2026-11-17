"""Attendance business logic: marking, statistics, and turning recognition results into records."""
import time
from collections import OrderedDict
from datetime import date, datetime, timedelta

from flask import current_app
from sqlalchemy import func

from extensions import db
from models.attendance import Attendance, PRESENT, LATE, ABSENT
from models.student import Student, Department
from face_engine.liveness import tracker
from utils import log_activity

_last_review_log = {"t": 0.0}


# ------------------------------------------------------------------ marking
def determine_status(now=None):
    now = now or datetime.now()
    hh, mm = current_app.config["LATE_AFTER"].split(":")
    cutoff = now.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
    return LATE if now > cutoff else PRESENT


def mark_attendance(student, status=None, confidence=None, method="face",
                    note=None, admin_id=None, when=None, overwrite=False):
    """Create today's record. Returns (record, created).

    One record per student per day. If it exists, nothing changes unless overwrite=True
    (used for authorised manual corrections).
    """
    when = when or datetime.now()
    day = when.date()
    record = Attendance.query.filter_by(student_id=student.id, date=day).first()
    if record and not overwrite:
        return record, False
    if record is None:
        record = Attendance(student_id=student.id, date=day)
        db.session.add(record)
    record.time = when.time().replace(microsecond=0)
    record.status = status or determine_status(when)
    record.method = method
    record.confidence = confidence
    record.note = note
    record.marked_by = admin_id
    db.session.commit()
    return record, True


def process_recognition(faces, admin_id=None):
    """Turn raw recognition results into client-ready results and mark attendance.

    Never penalises anyone for a failed match: unknown/ambiguous faces only create a
    'needs review' log entry. Absent is never written automatically.
    """
    out = []
    today = date.today()
    require_live = current_app.config["LIVENESS_REQUIRED"]
    for f in faces:
        item = {"box": f["box"], "confidence": f["confidence"], "distance": f["distance"],
                "name": "Unregistered", "student_code": "", "state": "unknown", "message": "Unregistered face"}
        if f["state"] == "ambiguous":
            item.update(name="Needs review", state="review", message="Match unclear. Ask an admin to check.")
            _log_review("Ambiguous face match")
        elif f["state"] == "unknown":
            _log_review("Unregistered face seen")
        else:
            student = db.session.get(Student, f["student_pk"])
            item.update(name=student.name, student_code=student.student_code)
            existing = Attendance.query.filter_by(student_id=student.id, date=today).first()
            if existing:
                item.update(state="already", message=f"Already marked {existing.status} at {existing.time.strftime('%H:%M')}")
            elif require_live and not tracker.update(student.id, f["ear"]):
                item.update(state="liveness", message="Blink once to verify")
            else:
                record, created = mark_attendance(student, confidence=f["confidence"],
                                                  method="face", admin_id=None)
                item.update(state="marked" if created else "already",
                            message=f"Marked {record.status} at {record.time.strftime('%H:%M')}")
                if created:
                    log_activity("attendance_marked", f"{student.student_code} {record.status} (face)", admin_id=admin_id)
                    db.session.commit()
        out.append(item)
    return out


def _log_review(text):
    """Log at most one review event per minute so the log is not flooded."""
    if time.time() - _last_review_log["t"] > 60:
        _last_review_log["t"] = time.time()
        log_activity("recognition_review", f"{text}. No penalty applied; review manually if needed.")
        db.session.commit()


# ------------------------------------------------------------------ queries
def query_records(date_from=None, date_to=None, department_id=None, status=None, search=None, limit=500):
    q = (db.session.query(Attendance, Student, Department)
         .join(Student, Student.id == Attendance.student_id)
         .outerjoin(Department, Department.id == Student.department_id))
    if date_from:
        q = q.filter(Attendance.date >= date_from)
    if date_to:
        q = q.filter(Attendance.date <= date_to)
    if department_id:
        q = q.filter(Student.department_id == department_id)
    if status:
        q = q.filter(Attendance.status == status)
    if search:
        like = f"%{search}%"
        q = q.filter(db.or_(Student.name.ilike(like), Student.student_code.ilike(like)))
    q = q.order_by(Attendance.date.desc(), Attendance.time.desc()).limit(limit)
    return q.all()


def record_to_dict(att, stu, dept):
    return {
        "id": att.id, "student_pk": stu.id, "student_code": stu.student_code, "name": stu.name,
        "department": dept.name if dept else "-", "date": att.date.isoformat(),
        "time": att.time.strftime("%H:%M:%S"), "status": att.status, "method": att.method,
        "confidence": att.confidence, "note": att.note or "",
    }


# ------------------------------------------------------------------ dashboard stats
def active_student_count():
    return Student.query.filter_by(active=True).count()


def today_stats(day=None):
    day = day or date.today()
    total = active_student_count()
    counts = dict(db.session.query(Attendance.status, func.count(Attendance.id))
                  .join(Student, Student.id == Attendance.student_id)
                  .filter(Attendance.date == day, Student.active.is_(True))
                  .group_by(Attendance.status).all())
    present, late = counts.get(PRESENT, 0), counts.get(LATE, 0)
    attended = present + late
    return {"total": total, "present": present, "late": late, "attended": attended,
            "absent": max(total - attended, 0),
            "percentage": round(attended / total * 100, 1) if total else 0.0}


def _attended_by_date(start, end):
    rows = (db.session.query(Attendance.date, func.count(Attendance.id))
            .filter(Attendance.date >= start, Attendance.date <= end,
                    Attendance.status.in_([PRESENT, LATE]))
            .group_by(Attendance.date).all())
    return {d: c for d, c in rows}


def series_daily(days=7):
    end = date.today()
    start = end - timedelta(days=days - 1)
    data = _attended_by_date(start, end)
    labels, values = [], []
    for i in range(days):
        d = start + timedelta(days=i)
        labels.append(d.strftime("%a %d"))
        values.append(data.get(d, 0))
    return {"labels": labels, "values": values}


def series_weekly(weeks=8):
    end = date.today()
    this_monday = end - timedelta(days=end.weekday())
    start = this_monday - timedelta(weeks=weeks - 1)
    data = _attended_by_date(start, end)
    buckets = OrderedDict((start + timedelta(weeks=i), 0) for i in range(weeks))
    for d, c in data.items():
        buckets[d - timedelta(days=d.weekday())] += c
    return {"labels": [k.strftime("%d %b") for k in buckets], "values": list(buckets.values())}


def series_monthly(months=6):
    end = date.today()
    first = end.replace(day=1)
    starts = []
    y, m = first.year, first.month
    for _ in range(months):
        starts.append(date(y, m, 1))
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    starts.reverse()
    data = _attended_by_date(starts[0], end)
    buckets = OrderedDict(((s.year, s.month), 0) for s in starts)
    for d, c in data.items():
        buckets[(d.year, d.month)] += c
    return {"labels": [date(y, m, 1).strftime("%b %Y") for (y, m) in buckets], "values": list(buckets.values())}


def department_today(day=None):
    day = day or date.today()
    rows = (db.session.query(Department.name, func.count(Student.id))
            .join(Student, Student.department_id == Department.id)
            .filter(Student.active.is_(True)).group_by(Department.name).all())
    totals = dict(rows)
    attended = dict(db.session.query(Department.name, func.count(Attendance.id))
                    .join(Student, Student.department_id == Department.id)
                    .join(Attendance, Attendance.student_id == Student.id)
                    .filter(Attendance.date == day, Attendance.status.in_([PRESENT, LATE]))
                    .group_by(Department.name).all())
    labels = sorted(totals)
    return {"labels": labels,
            "values": [round(attended.get(n, 0) / totals[n] * 100, 1) if totals[n] else 0 for n in labels]}

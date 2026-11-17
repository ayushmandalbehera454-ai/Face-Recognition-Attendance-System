from datetime import datetime
from sqlalchemy.orm import validates
from extensions import db

PRESENT, ABSENT, LATE = "Present", "Absent", "Late"
STATUSES = (PRESENT, LATE, ABSENT)
METHODS = ("face", "manual")


class Attendance(db.Model):
    __tablename__ = "attendance"
    __table_args__ = (db.UniqueConstraint("student_id", "date", name="uq_student_date"),)

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id", ondelete="CASCADE"),
                           nullable=False, index=True)
    date = db.Column(db.Date, nullable=False, index=True)
    time = db.Column(db.Time, nullable=False)
    status = db.Column(db.String(10), nullable=False, default=PRESENT)
    method = db.Column(db.String(10), nullable=False, default="face")
    confidence = db.Column(db.Float)          # 0-100, face method only
    note = db.Column(db.String(200))
    marked_by = db.Column(db.Integer, db.ForeignKey("admins.id", ondelete="SET NULL"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    student = db.relationship("Student", back_populates="attendance")

    @validates("status")
    def _check_status(self, key, value):
        if value not in STATUSES:
            raise ValueError(f"Status must be one of {STATUSES}")
        return value

    @validates("method")
    def _check_method(self, key, value):
        if value not in METHODS:
            raise ValueError(f"Method must be one of {METHODS}")
        return value

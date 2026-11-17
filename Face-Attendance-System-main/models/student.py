from datetime import datetime
from extensions import db


class Department(db.Model):
    __tablename__ = "departments"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    students = db.relationship("Student", back_populates="department")


class Student(db.Model):
    """A registered student or employee."""
    __tablename__ = "students"

    id = db.Column(db.Integer, primary_key=True)
    student_code = db.Column(db.String(30), unique=True, nullable=False, index=True)
    name = db.Column(db.String(80), nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey("departments.id"), nullable=True)
    consent_given = db.Column(db.Boolean, nullable=False, default=False)
    consent_at = db.Column(db.DateTime)
    active = db.Column(db.Boolean, nullable=False, default=True)
    registered_at = db.Column(db.DateTime, default=datetime.utcnow)

    department = db.relationship("Department", back_populates="students")
    embeddings = db.relationship("FaceEmbedding", back_populates="student",
                                 cascade="all, delete-orphan")
    attendance = db.relationship("Attendance", back_populates="student",
                                 cascade="all, delete-orphan")

    @property
    def has_face_data(self):
        return len(self.embeddings) > 0


class FaceEmbedding(db.Model):
    """One 128-number face vector, stored ENCRYPTED (Fernet) as bytes."""
    __tablename__ = "face_embeddings"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id", ondelete="CASCADE"),
                           nullable=False, index=True)
    encrypted_vector = db.Column(db.LargeBinary, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    student = db.relationship("Student", back_populates="embeddings")

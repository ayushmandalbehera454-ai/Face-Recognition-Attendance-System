from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from extensions import db, login_manager

ROLES = ("superadmin", "admin", "viewer")


class Admin(UserMixin, db.Model):
    __tablename__ = "admins"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False, index=True)
    full_name = db.Column(db.String(100), nullable=False, default="Administrator")
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="admin")
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)

    @property
    def is_active(self):  # Flask-Login hook
        return self.active

    @property
    def can_write(self):
        return self.role in ("superadmin", "admin")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)  # salted PBKDF2/scrypt

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f"<Admin {self.username} ({self.role})>"


class ActivityLog(db.Model):
    __tablename__ = "activity_logs"

    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey("admins.id", ondelete="SET NULL"), nullable=True)
    action = db.Column(db.String(60), nullable=False, index=True)
    details = db.Column(db.String(500), default="")
    ip_address = db.Column(db.String(45))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    admin = db.relationship("Admin", backref=db.backref("logs", lazy="dynamic"))


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(Admin, int(user_id))

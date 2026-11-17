"""Small helpers shared by routes and services."""
import re
from functools import wraps
from flask import jsonify, request, flash, redirect, url_for
from flask_login import current_user

from extensions import db

ID_RE = re.compile(r"^[A-Za-z0-9_-]{2,30}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
NAME_RE = re.compile(r"^[A-Za-z][A-Za-z .'-]{1,79}$")


def roles_required(*roles):
    """Allow only logged-in admins whose role is in `roles`. JSON for /api, redirect otherwise."""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                return current_app_login_required()
            if current_user.role not in roles:
                if request.path.startswith("/api/"):
                    return jsonify(error="You do not have permission to do this."), 403
                flash("You do not have permission to do this.", "danger")
                return redirect(url_for("dashboard.dashboard"))
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def current_app_login_required():
    if request.path.startswith("/api/"):
        return jsonify(error="Please log in."), 401
    return redirect(url_for("auth.login", next=request.path))


def log_activity(action, details="", admin_id=None):
    """Write an Activity_Logs row (committed by the caller's commit)."""
    from models.admin import ActivityLog
    if admin_id is None and current_user and current_user.is_authenticated:
        admin_id = current_user.id
    ip = request.remote_addr if request else None
    db.session.add(ActivityLog(admin_id=admin_id, action=action, details=details[:500], ip_address=ip))


# Full-access roles. "viewer" can look at data but not change anything.
WRITE_ROLES = ("superadmin", "admin")

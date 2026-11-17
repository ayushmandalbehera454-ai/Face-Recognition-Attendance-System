from datetime import datetime
from urllib.parse import urlparse

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user

from extensions import db
from models.admin import Admin
from utils import log_activity

bp = Blueprint("auth", __name__)


def _safe_next(target):
    """Only allow redirects to paths on this site (blocks open-redirect attacks)."""
    if target and target.startswith("/") and not target.startswith("//") and not urlparse(target).netloc:
        return target
    return None


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.dashboard"))
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        admin = Admin.query.filter_by(username=username).first()
        if admin and admin.active and admin.check_password(password):
            login_user(admin, remember=False)
            admin.last_login = datetime.utcnow()
            log_activity("login", f"{admin.username} logged in", admin_id=admin.id)
            db.session.commit()
            if admin.check_password("Admin@12345"):
                flash("You are using the default password. Please change it in Profile.", "warning")
            return redirect(_safe_next(request.args.get("next")) or url_for("dashboard.dashboard"))
        log_activity("login_failed", f"Failed login for '{username[:50]}'", admin_id=None)
        db.session.commit()
        flash("Wrong username or password.", "danger")
    return render_template("login.html")


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    log_activity("logout", f"{current_user.username} logged out")
    db.session.commit()
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))


@bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "details":
            name = (request.form.get("full_name") or "").strip()
            email = (request.form.get("email") or "").strip().lower()
            from utils import EMAIL_RE
            if len(name) < 2 or not EMAIL_RE.match(email):
                flash("Enter a valid name and email.", "danger")
            elif Admin.query.filter(Admin.email == email, Admin.id != current_user.id).first():
                flash("That email is already used by another admin.", "danger")
            else:
                current_user.full_name, current_user.email = name, email
                db.session.commit()
                flash("Profile updated.", "success")
        elif action == "password":
            old, new, confirm = (request.form.get(k) or "" for k in ("old_password", "new_password", "confirm_password"))
            if not current_user.check_password(old):
                flash("Current password is wrong.", "danger")
            elif len(new) < 8 or new.isalpha() or new.isdigit():
                flash("New password needs 8+ characters with letters and numbers.", "danger")
            elif new != confirm:
                flash("New passwords do not match.", "danger")
            else:
                current_user.set_password(new)
                log_activity("password_changed", current_user.username)
                db.session.commit()
                flash("Password changed.", "success")
        return redirect(url_for("auth.profile"))
    return render_template("profile.html")

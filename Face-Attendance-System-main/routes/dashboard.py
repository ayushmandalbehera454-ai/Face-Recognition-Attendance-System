from flask import Blueprint, render_template, jsonify
from flask_login import login_required

from models.admin import ActivityLog
from services import attendance_service as svc
from utils import roles_required

bp = Blueprint("dashboard", __name__)


@bp.route("/")
@bp.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html")


@bp.route("/api/dashboard/stats")
@login_required
def stats():
    recent = [svc.record_to_dict(*row) for row in svc.query_records(limit=10)]
    return jsonify(
        today=svc.today_stats(),
        daily=svc.series_daily(7),
        weekly=svc.series_weekly(8),
        monthly=svc.series_monthly(6),
        departments=svc.department_today(),
        recent=recent,
    )


@bp.route("/logs")
@roles_required("superadmin", "admin")
def logs():
    rows = ActivityLog.query.order_by(ActivityLog.created_at.desc()).limit(200).all()
    return render_template("logs.html", logs=rows)

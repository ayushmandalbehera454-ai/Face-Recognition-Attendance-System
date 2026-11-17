from datetime import datetime

from flask import Blueprint, render_template, request, jsonify, Response
from flask_login import login_required

from models.student import Student, Department
from services import report_service as rs

bp = Blueprint("reports", __name__)


@bp.route("/reports")
@login_required
def reports_page():
    return render_template("reports.html",
                           departments=Department.query.order_by(Department.name).all(),
                           students=Student.query.order_by(Student.name).all())


def _build():
    rtype = request.args.get("type", "daily")
    if rtype not in rs.REPORT_TYPES:
        raise ValueError("Unknown report type.")
    return rtype, rs.build_report(rtype, request.args)


@bp.route("/api/reports/data")
@login_required
def data():
    try:
        rtype, (title, df, chart) = _build()
    except ValueError as e:
        return jsonify(error=str(e)), 400
    return jsonify(title=title, columns=list(df.columns), rows=df.astype(object).where(df.notna(), "").values.tolist(), chart=chart)


@bp.route("/reports/export/<fmt>")
@login_required
def export(fmt):
    try:
        rtype, (title, df, chart) = _build()
    except ValueError as e:
        return Response(str(e), status=400)
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    name = f"attendance_{rtype}_{stamp}"
    if fmt == "csv":
        body, mime, ext = rs.to_csv(df), "text/csv", "csv"
    elif fmt == "xlsx":
        body, mime, ext = rs.to_xlsx(df, title), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "xlsx"
    elif fmt == "pdf":
        body, mime, ext = rs.to_pdf(df, title, chart), "application/pdf", "pdf"
    else:
        return Response("Unknown format", status=400)
    return Response(body, mimetype=mime, headers={"Content-Disposition": f'attachment; filename="{name}.{ext}"'})

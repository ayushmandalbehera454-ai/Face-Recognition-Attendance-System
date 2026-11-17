"""Builds report tables (pandas) and exports them to CSV, Excel and PDF."""
import io
from datetime import date, datetime, timedelta

import matplotlib
matplotlib.use("Agg")  # no display needed on a server
import matplotlib.pyplot as plt
import pandas as pd
from sqlalchemy import func

from extensions import db
from models.attendance import Attendance, PRESENT, LATE, ABSENT
from models.student import Student, Department

REPORT_TYPES = ("daily", "monthly", "individual", "department")


def _d(value, default):
    if not value:
        return default
    return datetime.strptime(value, "%Y-%m-%d").date()


def _working_dates(start, end):
    """Days on which attendance was taken at all (at least one record)."""
    rows = (db.session.query(Attendance.date)
            .filter(Attendance.date >= start, Attendance.date <= end).distinct().all())
    return sorted(r[0] for r in rows)


def _expected(student, working):
    reg = student.registered_at.date() if student.registered_at else date.min
    return [d for d in working if d >= reg]


def _dept_name(student):
    return student.department.name if student.department else "-"


def _pct(done, expected):
    return round(done / expected * 100, 1) if expected else 0.0


def build_report(rtype, params):
    """Return (title, DataFrame, chart) where chart = {'labels': [...], 'values': [...], 'label': str}."""
    if rtype == "daily":
        return _daily(_d(params.get("date"), date.today()), params)
    if rtype == "monthly":
        month = params.get("month") or date.today().strftime("%Y-%m")
        return _monthly(month)
    if rtype == "individual":
        today = date.today()
        return _individual(params.get("student"), _d(params.get("from"), today.replace(day=1)),
                           _d(params.get("to"), today))
    if rtype == "department":
        today = date.today()
        return _department(_d(params.get("from"), today.replace(day=1)), _d(params.get("to"), today))
    raise ValueError("Unknown report type")


def _daily(day, params):
    dept_id = params.get("department")
    students = Student.query.filter_by(active=True)
    if dept_id:
        students = students.filter_by(department_id=int(dept_id))
    records = {a.student_id: a for a in Attendance.query.filter_by(date=day).all()}
    rows = []
    for s in students.order_by(Student.name).all():
        a = records.get(s.id)
        rows.append({"Student ID": s.student_code, "Name": s.name, "Department": _dept_name(s),
                     "Status": a.status if a else ABSENT,
                     "Time": a.time.strftime("%H:%M") if a else "",
                     "Method": a.method if a else "",
                     "Confidence %": a.confidence if a and a.confidence is not None else ""})
    df = pd.DataFrame(rows, columns=["Student ID", "Name", "Department", "Status", "Time", "Method", "Confidence %"])
    counts = df["Status"].value_counts() if not df.empty else pd.Series(dtype=int)
    chart = {"labels": [PRESENT, LATE, ABSENT], "values": [int(counts.get(k, 0)) for k in (PRESENT, LATE, ABSENT)],
             "label": "Students"}
    return f"Daily Attendance Report - {day.isoformat()}", df, chart


def _monthly(month):
    first = datetime.strptime(month + "-01", "%Y-%m-%d").date()
    nxt = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
    last = nxt - timedelta(days=1)
    working = _working_dates(first, last)
    records = Attendance.query.filter(Attendance.date >= first, Attendance.date <= last).all()
    by_student = {}
    for a in records:
        by_student.setdefault(a.student_id, {})[a.date] = a.status
    rows = []
    for s in Student.query.filter_by(active=True).order_by(Student.name).all():
        days = _expected(s, working)
        mine = by_student.get(s.id, {})
        present = sum(1 for d in days if mine.get(d) == PRESENT)
        late = sum(1 for d in days if mine.get(d) == LATE)
        absent = len(days) - present - late
        rows.append({"Student ID": s.student_code, "Name": s.name, "Department": _dept_name(s),
                     "Working Days": len(days), "Present": present, "Late": late, "Absent": absent,
                     "Attendance %": _pct(present + late, len(days))})
    df = pd.DataFrame(rows, columns=["Student ID", "Name", "Department", "Working Days", "Present", "Late", "Absent", "Attendance %"])
    per_day = {d: 0 for d in working}
    for a in records:
        if a.status in (PRESENT, LATE) and a.date in per_day:
            per_day[a.date] += 1
    chart = {"labels": [d.strftime("%d") for d in working], "values": list(per_day.values()),
             "label": "Students attended per day"}
    return f"Monthly Attendance Report - {first.strftime('%B %Y')}", df, chart


def _individual(code, start, end):
    student = Student.query.filter_by(student_code=code).first() if code else None
    if not student:
        raise ValueError("Choose a student for the individual report.")
    working = _expected(student, _working_dates(start, end))
    mine = {a.date: a for a in Attendance.query.filter(
        Attendance.student_id == student.id, Attendance.date >= start, Attendance.date <= end).all()}
    rows = []
    for d in working:
        a = mine.get(d)
        rows.append({"Date": d.isoformat(), "Status": a.status if a else ABSENT,
                     "Time": a.time.strftime("%H:%M") if a else "", "Method": a.method if a else "",
                     "Confidence %": a.confidence if a and a.confidence is not None else ""})
    df = pd.DataFrame(rows, columns=["Date", "Status", "Time", "Method", "Confidence %"])
    counts = df["Status"].value_counts() if not df.empty else pd.Series(dtype=int)
    chart = {"labels": [PRESENT, LATE, ABSENT], "values": [int(counts.get(k, 0)) for k in (PRESENT, LATE, ABSENT)],
             "label": "Days"}
    return f"Attendance Report - {student.name} ({student.student_code}), {start} to {end}", df, chart


def _department(start, end):
    working = _working_dates(start, end)
    recs = Attendance.query.filter(Attendance.date >= start, Attendance.date <= end).all()
    by_student = {}
    for a in recs:
        by_student.setdefault(a.student_id, {})[a.date] = a.status
    rows = []
    for dept in Department.query.order_by(Department.name).all():
        present = late = expected = n = 0
        for s in dept.students:
            if not s.active:
                continue
            n += 1
            days = _expected(s, working)
            mine = by_student.get(s.id, {})
            p = sum(1 for d in days if mine.get(d) == PRESENT)
            l = sum(1 for d in days if mine.get(d) == LATE)
            present, late, expected = present + p, late + l, expected + len(days)
        rows.append({"Department": dept.name, "Students": n, "Present": present, "Late": late,
                     "Absent": expected - present - late, "Attendance %": _pct(present + late, expected)})
    df = pd.DataFrame(rows, columns=["Department", "Students", "Present", "Late", "Absent", "Attendance %"])
    chart = {"labels": list(df["Department"]), "values": list(df["Attendance %"]), "label": "Attendance %"}
    return f"Department-wise Attendance - {start} to {end}", df, chart


# ------------------------------------------------------------------ exports
def to_csv(df):
    return df.to_csv(index=False).encode("utf-8-sig")  # BOM so Excel opens it correctly


def to_xlsx(df, title):
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Report")
        ws = writer.sheets["Report"]
        for col in ws.columns:
            width = max(len(str(c.value)) if c.value is not None else 0 for c in col) + 3
            ws.column_dimensions[col[0].column_letter].width = min(width, 40)
    return buf.getvalue()


def _chart_png(chart):
    fig, ax = plt.subplots(figsize=(7, 2.8), dpi=130)
    labels = chart["labels"] or ["No data"]
    values = chart["values"] or [0]
    ax.bar(labels, values, color="#0F9D8A")
    ax.set_ylabel(chart.get("label", ""))
    ax.spines[["top", "right"]].set_visible(False)
    plt.xticks(rotation=45 if len(labels) > 8 else 0, fontsize=8)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)
    return buf


def to_pdf(df, title, chart):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=1.5 * cm, rightMargin=1.5 * cm,
                            topMargin=1.5 * cm, bottomMargin=1.5 * cm, title=title)
    styles = getSampleStyleSheet()
    story = [Paragraph(title, styles["Title"]),
             Paragraph(f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}", styles["Normal"]),
             Spacer(1, 0.4 * cm), Image(_chart_png(chart), width=17 * cm, height=6.8 * cm), Spacer(1, 0.4 * cm)]
    data = [list(df.columns)] + [[str(v) for v in row] for row in df.itertuples(index=False)]
    if len(data) == 1:
        data.append(["No records"] + [""] * (len(df.columns) - 1))
    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#14213D")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F1F4F8")]),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#C9D1DC")),
    ]))
    story.append(table)
    doc.build(story)
    return buf.getvalue()

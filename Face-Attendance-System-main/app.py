import os
import random
from datetime import date, datetime, time, timedelta

import click
from flask import Flask, jsonify, render_template, request, redirect, url_for

from config import config_by_name
from extensions import db, login_manager, csrf


def create_app(config_name=None):
    config_name = config_name or os.environ.get("FLASK_ENV", "development")
    app = Flask(__name__)
    app.config.from_object(config_by_name.get(config_name, config_by_name["development"]))

    for folder in (app.config["DATASET_FOLDER"], app.config["EXPORT_FOLDER"], app.config["DATABASE_FOLDER"]):
        os.makedirs(folder, exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    import models  # noqa: F401  (registers all tables)
    from routes import auth, dashboard, students, attendance, reports
    for module in (auth, dashboard, students, attendance, reports):
        app.register_blueprint(module.bp)

    @app.after_request
    def security_headers(resp):
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "SAMEORIGIN"
        resp.headers["Referrer-Policy"] = "same-origin"
        resp.headers["Permissions-Policy"] = "camera=(self)"
        return resp

    @login_manager.unauthorized_handler
    def unauthorized():
        if request.path.startswith("/api/"):
            return jsonify(error="Please log in."), 401
        return redirect(url_for("auth.login", next=request.path))

    @app.route("/health")
    def health():
        return jsonify(status="ok")

    @app.errorhandler(404)
    def not_found(e):
        if request.path.startswith("/api/"):
            return jsonify(error="Not found"), 404
        return render_template("error.html", code=404, message="That page does not exist."), 404

    @app.errorhandler(500)
    def server_error(e):
        if request.path.startswith("/api/"):
            return jsonify(error="Server error. Check the terminal for details."), 500
        return render_template("error.html", code=500, message="Something went wrong on the server."), 500

    with app.app_context():
        db.create_all()
        _seed_admin(app)

    _register_cli(app)
    return app


def _seed_admin(app):
    from models.admin import Admin
    if Admin.query.count() == 0:
        admin = Admin(username=app.config["ADMIN_USERNAME"], full_name="Super Admin",
                      email=app.config["ADMIN_EMAIL"], role="superadmin")
        admin.set_password(app.config["ADMIN_PASSWORD"])
        db.session.add(admin)
        db.session.commit()
        print(f"[setup] Created first admin '{admin.username}'. CHANGE THE PASSWORD after logging in.")


def _register_cli(app):
    @app.cli.command("create-admin")
    @click.argument("username")
    @click.argument("email")
    @click.option("--role", type=click.Choice(["superadmin", "admin", "viewer"]), default="admin")
    @click.password_option()
    def create_admin(username, email, role, password):
        """Create another admin or viewer account."""
        from models.admin import Admin
        if Admin.query.filter((Admin.username == username) | (Admin.email == email)).first():
            raise click.ClickException("Username or email already exists.")
        a = Admin(username=username, email=email, full_name=username, role=role)
        a.set_password(password)
        db.session.add(a)
        db.session.commit()
        click.echo(f"Created {role} '{username}'.")

    @app.cli.command("seed-demo")
    def seed_demo():
        """Add demo departments, people (no face data) and 20 days of attendance to try the dashboard."""
        from models.student import Department, Student
        from models.attendance import Attendance
        if Student.query.filter(Student.student_code.like("DEMO%")).count():
            click.echo("Demo data already exists.")
            return
        depts = [Department(name=n) for n in ("Computer Science", "Electronics", "Mechanical")
                 if not Department.query.filter_by(name=n).first()]
        db.session.add_all(depts)
        db.session.flush()
        all_depts = Department.query.all()
        names = ["Aarav Mehta", "Diya Sharma", "Rohan Das", "Ananya Iyer", "Kabir Singh", "Meera Nair",
                 "Ishaan Patel", "Sara Khan", "Vikram Rao", "Tanvi Joshi", "Arjun Reddy", "Neha Gupta"]
        people = []
        for i, n in enumerate(names, 1):
            s = Student(student_code=f"DEMO{i:03d}", name=n, email=f"demo{i}@example.com",
                        department_id=random.choice(all_depts).id, registered_at=datetime.now() - timedelta(days=30))
            db.session.add(s)
            people.append(s)
        db.session.flush()
        for back in range(20):
            day = date.today() - timedelta(days=back)
            if day.weekday() >= 5:
                continue
            for s in people:
                roll = random.random()
                if roll < 0.12:
                    continue
                late = roll > 0.85
                db.session.add(Attendance(student_id=s.id, date=day, status="Late" if late else "Present",
                                          time=time(9, random.randint(20, 55)) if late else time(8, random.randint(30, 59)),
                                          method="face", confidence=round(random.uniform(70, 96), 1)))
        db.session.commit()
        click.echo("Demo data added. People have no face data, so they are for dashboard/report testing only.")


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=5000, debug=True)

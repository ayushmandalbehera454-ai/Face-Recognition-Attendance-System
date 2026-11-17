# FaceTrack: Face Recognition Attendance System

Flask + OpenCV + `face_recognition` + SQLAlchemy + Bootstrap 5. Admins register people, a webcam
recognises them, and attendance is marked automatically with dashboards, charts and Excel/CSV/PDF reports.

## Features
- Admin login (hashed passwords, CSRF protection, roles: `superadmin`, `admin`, `viewer`)
- Register people with webcam face capture, edit, delete, search, departments
- Live multi-face recognition showing name, ID, match % and distance; unknown faces shown as "Unregistered"
- Automatic Present / Late marking, one record per person per day, manual corrections with a reason
- Dashboard: totals, present/absent today, percentage, daily/weekly/monthly charts, recent records
- Reports: daily, monthly, individual, department-wise; export CSV, Excel, PDF
- Dark/light mode, responsive layout, live notifications, activity log

## Privacy and fairness (built in)
- Consent checkbox before any face data is stored; **no consent = manual attendance** (non-biometric option)
- Only **encrypted 128-number embeddings** are stored (Fernet key in `.env` or `database/embedding.key`), no photos
- "Withdraw consent" erases a person's face data
- A face that is unknown or unclear is **never marked absent**. It is logged for human review
- Ambiguous matches (two similar people) go to manual review instead of guessing
- Blink-based liveness check reduces photo spoofing (not foolproof, see Limitations)

## Install
Needs Python 3.10 or 3.11.

```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install cmake                 # needed to build dlib
pip install -r requirements.txt
cp .env.example .env              # Windows: copy .env.example .env
```
`dlib` build tools: Ubuntu `sudo apt install build-essential cmake`, macOS `brew install cmake`,
Windows install Visual Studio Build Tools ("Desktop development with C++").

Generate secrets and paste them into `.env`:
```bash
python -c "import secrets; print(secrets.token_hex(32))"                              # SECRET_KEY
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"   # EMBEDDING_KEY
```
Keep `EMBEDDING_KEY` safe. Without it, stored face data cannot be read.

## Run
```bash
python app.py
```
Open http://127.0.0.1:5000 and sign in with `admin` / `Admin@12345` (from `.env`). **Change the password in Profile.**
The camera works on `localhost` or HTTPS only.

Try the dashboard without cameras: `flask --app app seed-demo`
Create more admins: `flask --app app create-admin alice alice@example.com --role viewer`

## Use
1. Departments > add departments
2. Register person > tick consent > Start camera > Auto-capture 5 photos > Register
3. Attendance > Start recognition > look at the camera and blink once
4. Dashboard and Reports show the results

Settings in `.env`: `MATCH_THRESHOLD` (lower is stricter, default 0.50), `LATE_AFTER` (default 09:15),
`LIVENESS_REQUIRED` (true/false).

## Tests
```bash
pytest -v
```

## Deploy
- Use HTTPS (browsers block cameras on plain http). Put Nginx or Caddy in front.
- Set `FLASK_ENV=production`, a strong `SECRET_KEY`, and change the admin password.
- Run with **one worker and several threads** (the liveness tracker and embedding cache live in memory):
  `gunicorn "app:create_app()" -w 1 --threads 4 -b 0.0.0.0:8000`
- MySQL: `pip install PyMySQL`, set `DATABASE_URL=mysql+pymysql://user:pass@localhost/attendance`
- Back up the database **and** the encryption key separately.

## Limitations (honest)
- Blink check stops printed photos and still images, but a video replay can fool it. Use a human check for high-security needs.
- Face recognition can be less accurate for some people and lighting. That is why unknown matches go to manual review and are never penalised.
- Check local privacy law (GDPR, DPDP Act, etc.) before collecting biometric data.

## Structure
```
app.py  config.py  extensions.py  utils.py
models/      admin.py student.py attendance.py
routes/      auth.py dashboard.py students.py attendance.py reports.py
face_engine/ face_detection.py face_encoding.py liveness.py recognition.py
services/    attendance_service.py report_service.py
templates/  static/{css,js}  dataset/  exports/  database/  tests/
```
(`face_engine` is named so it does not shadow the `face_recognition` library.)

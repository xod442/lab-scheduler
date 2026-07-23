"""
Lab Scheduler portal.

Public:
  /            welcome page -> "Schedule a Lab" button
  /schedule    calendar of upcoming lab sessions as selectable pills

Shadow admin console (unadvertised path, own login, Opal-style security):
  {ADMIN_PATH}/login          admin sign-in
  {ADMIN_PATH}                 dashboard: API key status + update, data source
  {ADMIN_PATH}/api-key         (POST) rotate the scheduler API key (Fernet-encrypted)
  {ADMIN_PATH}/password        force/allow password change
  {ADMIN_PATH}/logout
"""
import json
import os
import sqlite3
from datetime import datetime, timedelta

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from passlib.context import CryptContext
from cryptography.fernet import Fernet, InvalidToken

import vlab_client

# ── Config ───────────────────────────────────────────────────────────────────
ROOT_PATH   = os.getenv("ROOT_PATH", "")
# Shadow admin base path — unadvertised; set to something obscure in prod.
ADMIN_PATH  = "/" + os.getenv("ADMIN_PATH", "admin").strip("/")
SECRET_KEY  = os.getenv("SECRET_KEY", "labportal-change-me-in-production")
SESSION_MAX_AGE = 8 * 3600
DB_PATH     = os.getenv("DB_PATH", os.path.join(os.path.dirname(__file__), "data", "labportal.db"))
FERNET_KEY_PATH = os.getenv("FERNET_KEY_PATH", os.path.join(os.path.dirname(__file__), "data", "secret.key"))
COOKIE_NAME   = "labportal_session"
COOKIE_PATH   = ROOT_PATH or "/"
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "true").strip().lower() != "false"

os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

pwd_ctx    = CryptContext(schemes=["bcrypt"], deprecated="auto")
serializer = URLSafeTimedSerializer(SECRET_KEY)


# ── Secret encryption (Fernet), same approach as Opal ─────────────────────────
def _load_fernet() -> Fernet:
    key = os.getenv("LABPORTAL_FERNET_KEY", "").strip()
    if not key:
        if os.path.exists(FERNET_KEY_PATH):
            with open(FERNET_KEY_PATH) as f:
                key = f.read().strip()
        else:
            key = Fernet.generate_key().decode()
            os.makedirs(os.path.dirname(FERNET_KEY_PATH), exist_ok=True)
            with open(FERNET_KEY_PATH, "w") as f:
                f.write(key)
            try:
                os.chmod(FERNET_KEY_PATH, 0o600)
            except OSError:
                pass
    return Fernet(key.encode())


fernet = _load_fernet()


def encrypt_secret(plaintext: str) -> str:
    return fernet.encrypt(plaintext.encode()).decode() if plaintext else ""


def decrypt_secret(token: str) -> str:
    if not token:
        return ""
    try:
        return fernet.decrypt(token.encode()).decode()
    except InvalidToken:
        return token


# ── DB / settings ─────────────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS admin_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            must_change_password INTEGER NOT NULL DEFAULT 0,
            created_at TEXT
        )
    """)
    conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL DEFAULT '')")
    # Transaction log — one row per reservation attempt (success or failure).
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reservation_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT, user_id TEXT, course_code TEXT, start_dt TEXT, end_dt TEXT,
            tz TEXT, num_students INTEGER, notes TEXT, res_id TEXT, action TEXT,
            status_code INTEGER, ok INTEGER, response TEXT, client_ip TEXT
        )
    """)
    for col in ("res_id TEXT", "action TEXT"):  # add to pre-existing tables
        try:
            conn.execute(f"ALTER TABLE reservation_log ADD COLUMN {col}")
        except sqlite3.OperationalError:
            pass
    if conn.execute("SELECT COUNT(*) FROM admin_users").fetchone()[0] == 0:
        # Default admin/admin, must change on first login (same as Opal).
        conn.execute(
            "INSERT INTO admin_users (username, password_hash, must_change_password, created_at) VALUES (?,?,1,?)",
            ("admin", pwd_ctx.hash("admin"), datetime.now().isoformat()),
        )
    conn.commit()
    conn.close()


init_db()


def get_setting(key: str, default: str = "") -> str:
    conn = get_db()
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row[0] if row else default


def set_setting(key: str, value: str):
    conn = get_db()
    conn.execute("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                 (key, value))
    conn.commit()
    conn.close()


def get_api_key() -> str:
    """Effective scheduler API key: stored (encrypted) value wins, else env fallback."""
    return decrypt_secret(get_setting("scheduler_api_key", "")) or vlab_client.SCHEDULER_API_KEY


# ── Admin session (Opal-style signed cookie) ──────────────────────────────────
def get_admin(request: Request):
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    try:
        return serializer.loads(token, max_age=SESSION_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None


def set_admin_cookie(response, username: str):
    token = serializer.dumps({"username": username})
    response.set_cookie(COOKIE_NAME, token, httponly=True, samesite="lax",
                        secure=COOKIE_SECURE, path=COOKIE_PATH, max_age=SESSION_MAX_AGE)


# ── App ────────────────────────────────────────────────────────────────────────
app = FastAPI(title="Lab Scheduler", root_path=ROOT_PATH)
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))
templates.env.globals["rp"] = ROOT_PATH
templates.env.globals["admin_path"] = ADMIN_PATH


# ---- Public ----
@app.get("/", response_class=HTMLResponse)
def welcome(request: Request):
    return templates.TemplateResponse(request=request, name="welcome.html", context={})


@app.get("/schedule", response_class=HTMLResponse)
def schedule(request: Request):
    api_key = get_api_key()
    error = ""
    cal = {"weeks": [], "session_count": 0, "range_label": ""}
    try:
        payload = vlab_client.fetch_items(api_key)
        cal = vlab_client.build_calendar(payload)
    except Exception as exc:  # network error, bad/expired key, API down, etc.
        print(f"[schedule] scheduler fetch failed: {type(exc).__name__}: {exc}")
        error = ("We couldn't load lab sessions right now. The scheduler may be "
                 "unavailable or the API key needs attention. Please try again shortly.")

    # Course-code "decoder ring", grouped by TE family (TE1/TE2/TE3/TE4).
    groups: dict = {}
    for c in vlab_client.load_catalog():
        groups.setdefault(c["code"][:3].upper(), []).append(c)
    catalog_groups = [{"family": fam, "courses": groups[fam]} for fam in sorted(groups)]

    return templates.TemplateResponse(
        request=request, name="schedule.html",
        context={"weeks": cal["weeks"], "session_count": cal["session_count"],
                 "range_label": cal["range_label"], "live": bool(api_key), "error": error,
                 "catalog_groups": catalog_groups},
    )


def _load_timezones() -> list:
    try:
        with open(os.path.join(os.path.dirname(__file__), "timezones.json")) as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return ["America/New_York", "UTC"]


TZ_CHOICES = _load_timezones()          # full IANA list the scheduler accepts
DEFAULT_TZ = os.getenv("DEFAULT_TZ", "America/New_York")
# "Schedule your own" collects only a start date/time; the end defaults to this
# many hours later (overridable).
OWN_DURATION_HOURS = int(os.getenv("OWN_DURATION_HOURS", "8"))


def _plus_hours(api_dt: str, hours: int) -> str:
    """Given a 'YYYY-MM-DD HH:MM:SS' string, return it + hours in the same format."""
    try:
        return (datetime.strptime(api_dt, "%Y-%m-%d %H:%M:%S") + timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return ""


def _api_dt(value: str) -> str:
    """Normalize a form datetime to the scheduler's 'YYYY-MM-DD HH:MM:SS' format."""
    s = (value or "").replace("T", " ").strip()
    if len(s) == 16:      # 'YYYY-MM-DD HH:MM' -> add seconds
        s += ":00"
    return s


def log_reservation(request: Request, payload: dict, result: dict, action: str = "create"):
    conn = get_db()
    conn.execute(
        """INSERT INTO reservation_log
           (ts, user_id, course_code, start_dt, end_dt, tz, num_students, notes,
            res_id, action, status_code, ok, response, client_ip)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (datetime.now().isoformat(), payload.get("userId"), payload.get("courseCode"),
         payload.get("startDateTime"), payload.get("endDateTime"), payload.get("tz"),
         payload.get("numStudents"), payload.get("notes"), payload.get("resId"), action,
         result.get("status_code"), 1 if result.get("ok") else 0,
         json.dumps(result.get("raw"))[:4000],
         request.client.host if request.client else ""),
    )
    conn.commit()
    conn.close()


@app.get("/reserve", response_class=HTMLResponse)
def reserve_form(request: Request):
    q = request.query_params

    def to_local(s: str) -> str:  # 'YYYY-MM-DD HH:MM' -> datetime-local value
        return s.replace(" ", "T")[:16] if s else ""

    return templates.TemplateResponse(
        request=request, name="reserve.html",
        context={"code": q.get("code", ""), "title": q.get("title", ""),
                 "start": to_local(q.get("start", "")), "end": to_local(q.get("end", "")),
                 "join": q.get("join", "") == "1",
                 "res_id": q.get("rid", ""),
                 "location": q.get("loc", ""),
                 "tz_choices": TZ_CHOICES, "tz_fixed": q.get("tz") or DEFAULT_TZ,
                 "catalog": vlab_client.load_catalog(),
                 "own_hours": OWN_DURATION_HOURS,
                 "live": bool(get_api_key())},
    )


@app.post("/reserve", response_class=HTMLResponse)
def reserve_submit(
    request: Request,
    courseCode: str = Form(...),
    userId: str = Form(...),
    startDateTime: str = Form(""),
    endDateTime: str = Form(""),
    tz: str = Form("America/New_York"),
    numStudents: int = Form(1),
    notes: str = Form(""),
    join: str = Form(""),
    resId: str = Form(""),
):
    if join == "1":
        # Join an EXISTING reservation: the scheduler gets resId + data.
        # Seats hard-capped at 1 (student adds only themselves).
        data = {"userId": userId.strip(), "comment": notes.strip(), "seats": 1}
        result = vlab_client.join_reservation(resId.strip(), data, get_api_key())
        payload = {  # for the transaction log / result display
            "userId": userId.strip(), "courseCode": courseCode.strip(),
            "startDateTime": _api_dt(startDateTime), "endDateTime": _api_dt(endDateTime),
            "tz": (tz.strip() or DEFAULT_TZ), "numStudents": 1,
            "notes": notes.strip(), "resId": resId.strip(),
        }
        log_reservation(request, payload, result, action="join")
    else:
        # Own workshop: student picks a start date/time; end defaults to +N hours.
        start_api = _api_dt(startDateTime)
        payload = {
            "userId": userId.strip(), "courseCode": courseCode.strip(),
            "startDateTime": start_api,
            "endDateTime": _plus_hours(start_api, OWN_DURATION_HOURS),
            "tz": (tz.strip() or DEFAULT_TZ), "numStudents": 1,
            "notes": notes.strip(), "resId": "",
        }
        result = vlab_client.create_reservation(payload, get_api_key())
        log_reservation(request, payload, result, action="create")
    return templates.TemplateResponse(
        request=request, name="reserve_result.html",
        context={"result": result, "payload": payload},
    )


@app.get("/health")
def health():
    return {"status": "ok"}


# ---- Shadow admin console ----
def _admin_url(suffix: str = "") -> str:
    return f"{ROOT_PATH}{ADMIN_PATH}{suffix}"


@app.get(ADMIN_PATH + "/login", response_class=HTMLResponse)
def admin_login_page(request: Request):
    if get_admin(request):
        return RedirectResponse(url=_admin_url(), status_code=303)
    return templates.TemplateResponse(request=request, name="admin_login.html",
                                      context={"error": "", "msg": request.query_params.get("msg", "")})


@app.post(ADMIN_PATH + "/login")
def admin_login(request: Request, username: str = Form(...), password: str = Form(...)):
    conn = get_db()
    u = conn.execute("SELECT * FROM admin_users WHERE username = ?", (username,)).fetchone()
    conn.close()
    if not u or not pwd_ctx.verify(password, u["password_hash"]):
        return templates.TemplateResponse(request=request, name="admin_login.html",
                                          context={"error": "Invalid username or password.", "msg": ""},
                                          status_code=401)
    dest = _admin_url("/password") if u["must_change_password"] else _admin_url()
    resp = RedirectResponse(url=dest, status_code=303)
    set_admin_cookie(resp, u["username"])
    return resp


@app.get(ADMIN_PATH, response_class=HTMLResponse)
def admin_home(request: Request):
    s = get_admin(request)
    if not s:
        return RedirectResponse(url=_admin_url("/login"), status_code=303)
    key = get_api_key()
    masked = (key[:4] + "…" + key[-4:]) if len(key) > 10 else ("•••• set" if key else "")
    from_env = bool(vlab_client.SCHEDULER_API_KEY) and not decrypt_secret(get_setting("scheduler_api_key", ""))
    return templates.TemplateResponse(
        request=request, name="admin.html",
        context={"username": s["username"], "key_set": bool(key), "key_masked": masked,
                 "from_env": from_env, "live": bool(key), "msg": request.query_params.get("msg", "")},
    )


@app.post(ADMIN_PATH + "/api-key")
def admin_update_key(request: Request, api_key: str = Form("")):
    if not get_admin(request):
        return RedirectResponse(url=_admin_url("/login"), status_code=303)
    api_key = api_key.strip()
    set_setting("scheduler_api_key", encrypt_secret(api_key))
    msg = "API+key+updated" if api_key else "API+key+cleared+(back+to+env/simulate)"
    return RedirectResponse(url=_admin_url(f"?msg={msg}"), status_code=303)


@app.get(ADMIN_PATH + "/password", response_class=HTMLResponse)
def admin_password_page(request: Request):
    s = get_admin(request)
    if not s:
        return RedirectResponse(url=_admin_url("/login"), status_code=303)
    return templates.TemplateResponse(request=request, name="admin_password.html", context={"error": ""})


@app.post(ADMIN_PATH + "/password")
def admin_password_save(request: Request, new_password: str = Form(...), confirm_password: str = Form(...)):
    s = get_admin(request)
    if not s:
        return RedirectResponse(url=_admin_url("/login"), status_code=303)
    err = None
    if len(new_password) < 8:
        err = "Password must be at least 8 characters."
    elif new_password != confirm_password:
        err = "Passwords do not match."
    if err:
        return templates.TemplateResponse(request=request, name="admin_password.html",
                                          context={"error": err}, status_code=400)
    conn = get_db()
    conn.execute("UPDATE admin_users SET password_hash = ?, must_change_password = 0 WHERE username = ?",
                 (pwd_ctx.hash(new_password), s["username"]))
    conn.commit()
    conn.close()
    return RedirectResponse(url=_admin_url("?msg=Password+updated"), status_code=303)


@app.get(ADMIN_PATH + "/logout")
def admin_logout():
    resp = RedirectResponse(url=_admin_url("/login"), status_code=303)
    resp.delete_cookie(COOKIE_NAME, path=COOKIE_PATH)
    return resp

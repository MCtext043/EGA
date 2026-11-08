import json
import os
import sqlite3
import time
from datetime import date, datetime, timezone
from pathlib import Path
from threading import Lock
from urllib.parse import parse_qs

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, field_validator

from app.admin import make_session, valid_session, verify_password


ROOT = Path(__file__).resolve().parent.parent
CONTENT_PATH = Path(os.getenv("CONTENT_PATH", ROOT / "app" / "content.json"))
DATABASE_PATH = Path(os.getenv("DATABASE_PATH", ROOT / "data" / "leads.sqlite3"))
templates = Jinja2Templates(directory=str(ROOT / "app" / "templates"))
app = FastAPI(title="Егор — ведущий мероприятий", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=str(ROOT / "app" / "static")), name="static")
_attempts: dict[str, list[float]] = {}
_attempts_lock = Lock()
_login_attempts: dict[str, list[float]] = {}
_login_lock = Lock()


def content() -> dict:
    with CONTENT_PATH.open(encoding="utf-8") as file:
        return json.load(file)


def base_url(request: Request) -> str:
    configured = os.getenv("SITE_URL", "").rstrip("/")
    return configured or str(request.base_url).rstrip("/")


def init_db() -> None:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DATABASE_PATH) as db:
        db.execute("""CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            name TEXT NOT NULL,
            contact TEXT NOT NULL,
            event_type TEXT NOT NULL,
            event_date TEXT NOT NULL,
            message TEXT NOT NULL,
            utm_source TEXT NOT NULL,
            utm_medium TEXT NOT NULL,
            utm_campaign TEXT NOT NULL
        )""")


class Lead(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    contact: str = Field(min_length=5, max_length=160)
    event_type: str = Field(min_length=2, max_length=80)
    event_date: date
    message: str = Field(default="", max_length=2000)
    consent: bool
    website: str = Field(default="", max_length=200)
    utm_source: str = Field(default="", max_length=160)
    utm_medium: str = Field(default="", max_length=160)
    utm_campaign: str = Field(default="", max_length=160)

    @field_validator("name", "contact", "event_type")
    @classmethod
    def not_blank(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise ValueError("Поле не заполнено")
        return value

    @field_validator("contact")
    @classmethod
    def valid_contact(cls, value: str) -> str:
        if len(value) < 5 or not (any(c.isdigit() for c in value) or "@" in value):
            raise ValueError("Укажите телефон или адрес для связи")
        return value

    @field_validator("event_date")
    @classmethod
    def future_date(cls, value: date) -> date:
        if value < date.today():
            raise ValueError("Дата мероприятия уже прошла")
        return value

    @field_validator("consent")
    @classmethod
    def requires_consent(cls, value: bool) -> bool:
        if not value:
            raise ValueError("Необходимо согласие на обработку данных")
        return value


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(request, "index.html", {
        "site": content(), "base_url": base_url(request),
        "metrika_id": os.getenv("YANDEX_METRIKA_ID", ""),
    })


@app.get("/privacy", response_class=HTMLResponse)
def privacy(request: Request):
    return templates.TemplateResponse(request, "privacy.html", {"site": content()})


@app.get("/robots.txt")
def robots(request: Request):
    return Response(f"User-agent: *\nAllow: /\nDisallow: /api/\nDisallow: /admin\nSitemap: {base_url(request)}/sitemap.xml\n", media_type="text/plain")


@app.get("/sitemap.xml")
def sitemap(request: Request):
    url = base_url(request)
    xml = f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>{url}/</loc></url><url><loc>{url}/privacy</loc></url></urlset>'
    return Response(xml, media_type="application/xml")


@app.get("/health")
def health():
    return {"status": "ok"}


def admin_configured() -> bool:
    return bool(os.getenv("ADMIN_PASSWORD_HASH")) and len(os.getenv("ADMIN_SESSION_SECRET", "")) >= 32


def admin_headers(response: Response) -> Response:
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response


def admin_authenticated(request: Request) -> bool:
    return valid_session(request.cookies.get("admin_session"), os.getenv("ADMIN_SESSION_SECRET", ""))


def login_page(request: Request, error: str = "", status_code: int = 200) -> Response:
    response = templates.TemplateResponse(request, "admin_login.html", {"error": error}, status_code=status_code)
    return admin_headers(response)


@app.get("/admin/login", response_class=HTMLResponse)
def admin_login_page(request: Request):
    if not admin_configured():
        return login_page(request, "Админка ещё не настроена. Укажите пароль и секрет сессии в .env.", 503)
    if admin_authenticated(request):
        return admin_headers(RedirectResponse("/admin", status_code=303))
    return login_page(request)


@app.post("/admin/login")
async def admin_login(request: Request):
    if not admin_configured():
        return login_page(request, "Админка ещё не настроена.", 503)
    origin = request.headers.get("origin", "").rstrip("/")
    if origin and origin != base_url(request):
        raise HTTPException(403, "Недопустимый источник запроса")
    client_ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    with _login_lock:
        recent = [moment for moment in _login_attempts.get(client_ip, []) if now - moment < 900]
        if len(recent) >= 5:
            return login_page(request, "Слишком много попыток. Попробуйте через 15 минут.", 429)
        _login_attempts[client_ip] = recent
    fields = parse_qs((await request.body()).decode("utf-8", "replace"), keep_blank_values=True)
    password = fields.get("password", [""])[0][:200]
    if not verify_password(password, os.getenv("ADMIN_PASSWORD_HASH", "")):
        with _login_lock:
            _login_attempts[client_ip].append(now)
        return login_page(request, "Неверный пароль.", 401)
    with _login_lock:
        _login_attempts.pop(client_ip, None)
    response = admin_headers(RedirectResponse("/admin", status_code=303))
    response.set_cookie(
        "admin_session", make_session(os.environ["ADMIN_SESSION_SECRET"]),
        max_age=8 * 60 * 60, httponly=True, samesite="strict",
        secure=base_url(request).startswith("https://"), path="/admin",
    )
    return response


@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request, q: str = "", page: int = 1):
    if not admin_configured():
        return admin_headers(RedirectResponse("/admin/login", status_code=303))
    if not admin_authenticated(request):
        return admin_headers(RedirectResponse("/admin/login", status_code=303))
    init_db()
    q = q.strip()[:100]
    page = max(1, min(page, 10000))
    where = "WHERE name LIKE ? OR contact LIKE ? OR event_type LIKE ?" if q else ""
    params = (f"%{q}%",) * 3 if q else ()
    with sqlite3.connect(DATABASE_PATH) as db:
        db.row_factory = sqlite3.Row
        total = db.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
        found = db.execute(f"SELECT COUNT(*) FROM leads {where}", params).fetchone()[0]
        upcoming = db.execute("SELECT COUNT(*) FROM leads WHERE event_date >= ?", (date.today().isoformat(),)).fetchone()[0]
        leads = [dict(row) for row in db.execute(
            f"SELECT * FROM leads {where} ORDER BY id DESC LIMIT 50 OFFSET ?", (*params, (page - 1) * 50)
        ).fetchall()]
    response = templates.TemplateResponse(request, "admin_dashboard.html", {
        "leads": leads, "total": total, "found": found, "upcoming": upcoming,
        "q": q, "page": page, "pages": max(1, (found + 49) // 50),
    })
    return admin_headers(response)


@app.post("/admin/logout")
def admin_logout(request: Request):
    origin = request.headers.get("origin", "").rstrip("/")
    if origin and origin != base_url(request):
        raise HTTPException(403, "Недопустимый источник запроса")
    response = admin_headers(RedirectResponse("/admin/login", status_code=303))
    response.delete_cookie("admin_session", path="/admin")
    return response


@app.post("/api/leads", status_code=201)
def create_lead(lead: Lead, request: Request):
    if lead.website.strip():
        raise HTTPException(400, "Заявка отклонена")
    expected_origin = os.getenv("SITE_URL", "").rstrip("/")
    origin = request.headers.get("origin", "").rstrip("/")
    if expected_origin and origin and origin != expected_origin:
        raise HTTPException(403, "Недопустимый источник запроса")
    client_ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    with _attempts_lock:
        recent = [moment for moment in _attempts.get(client_ip, []) if now - moment < 3600]
        if len(recent) >= 5:
            raise HTTPException(429, "Слишком много заявок. Попробуйте позже.")
        recent.append(now)
        _attempts[client_ip] = recent
    init_db()
    with sqlite3.connect(DATABASE_PATH) as db:
        cursor = db.execute(
            "INSERT INTO leads (created_at,name,contact,event_type,event_date,message,utm_source,utm_medium,utm_campaign) VALUES (?,?,?,?,?,?,?,?,?)",
            (datetime.now(timezone.utc).isoformat(), lead.name, lead.contact, lead.event_type,
             lead.event_date.isoformat(), lead.message.strip(), lead.utm_source,
             lead.utm_medium, lead.utm_campaign),
        )
        return {"status": "saved", "id": cursor.lastrowid}

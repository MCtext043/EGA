import json
import os
import sqlite3
import time
from datetime import date, datetime, timezone
from pathlib import Path
from threading import Lock
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, field_validator


ROOT = Path(__file__).resolve().parent.parent
CONTENT_PATH = Path(os.getenv("CONTENT_PATH", ROOT / "app" / "content.json"))
DATABASE_PATH = Path(os.getenv("DATABASE_PATH", ROOT / "data" / "leads.sqlite3"))
templates = Jinja2Templates(directory=str(ROOT / "app" / "templates"))
app = FastAPI(title="Егор — ведущий мероприятий", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=str(ROOT / "app" / "static")), name="static")
_attempts: dict[str, list[float]] = {}
_attempts_lock = Lock()


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
    return Response(f"User-agent: *\nAllow: /\nDisallow: /api/\nSitemap: {base_url(request)}/sitemap.xml\n", media_type="text/plain")


@app.get("/sitemap.xml")
def sitemap(request: Request):
    url = base_url(request)
    xml = f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>{url}/</loc></url><url><loc>{url}/privacy</loc></url></urlset>'
    return Response(xml, media_type="application/xml")


@app.get("/health")
def health():
    return {"status": "ok"}


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

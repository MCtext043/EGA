import os
import sqlite3
import tempfile
from pathlib import Path

os.environ["DATABASE_PATH"] = str(Path(tempfile.mkdtemp()) / "admin-test.sqlite3")

from fastapi.testclient import TestClient

from app.main import DATABASE_PATH, app, init_db
from app.admin import hash_password


def test_admin_requires_login(monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", hash_password("correct horse battery staple"))
    monkeypatch.setenv("ADMIN_SESSION_SECRET", "s" * 64)
    with TestClient(app) as client:
        response = client.get("/admin", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/admin/login"
        assert client.get("/admin/login").status_code == 200


def test_login_leads_filter_and_logout(monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", hash_password("correct horse battery staple"))
    monkeypatch.setenv("ADMIN_SESSION_SECRET", "s" * 64)
    init_db()
    with sqlite3.connect(DATABASE_PATH) as db:
        db.execute("INSERT INTO leads (created_at,name,contact,event_type,event_date,message,utm_source,utm_medium,utm_campaign) VALUES (?,?,?,?,?,?,?,?,?)",
                   ("2026-11-08T10:00:00+00:00", "Анна", "anna@example.com", "Свадьба", "2027-06-12", "40 гостей", "direct", "cpc", "autumn"))
    with TestClient(app) as client:
        wrong = client.post("/admin/login", data={"password": "wrong"}, follow_redirects=False)
        assert wrong.status_code == 401
        assert "admin_session" not in wrong.cookies

        login = client.post("/admin/login", data={"password": "correct horse battery staple"}, follow_redirects=False)
        assert login.status_code == 303
        assert login.headers["location"] == "/admin"
        assert login.cookies.get("admin_session")

        dashboard = client.get("/admin")
        assert dashboard.status_code == 200
        assert "Анна" in dashboard.text
        assert "anna@example.com" in dashboard.text
        assert "direct" in dashboard.text
        assert dashboard.headers["cache-control"] == "no-store"

        filtered = client.get("/admin?q=несуществующий")
        assert "anna@example.com" not in filtered.text
        assert client.post("/admin/logout", follow_redirects=False).status_code == 303
        assert client.get("/admin", follow_redirects=False).status_code == 303


def test_admin_disabled_without_configuration(monkeypatch):
    monkeypatch.delenv("ADMIN_PASSWORD_HASH", raising=False)
    monkeypatch.delenv("ADMIN_SESSION_SECRET", raising=False)
    with TestClient(app) as client:
        assert client.get("/admin/login").status_code == 503

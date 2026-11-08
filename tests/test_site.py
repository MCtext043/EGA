import os
import sqlite3
import tempfile
from pathlib import Path

os.environ["DATABASE_PATH"] = str(Path(tempfile.mkdtemp()) / "leads.sqlite3")

from fastapi.testclient import TestClient

from app.main import DATABASE_PATH, app


client = TestClient(app)


def valid_lead(**changes):
    data = {
        "name": "Анна",
        "contact": "+7 900 123-45-67",
        "event_type": "Свадьба",
        "event_date": "2027-06-12",
        "message": "Около 40 гостей",
        "consent": True,
        "website": "",
        "utm_source": "direct",
    }
    data.update(changes)
    return data


def test_home_and_metadata():
    response = client.get("/")
    assert response.status_code == 200
    assert "ведущий мероприятий в Ижевске" in response.text
    assert 'name="description"' in response.text
    assert 'id="lead-form"' in response.text


def test_lead_is_persisted():
    response = client.post("/api/leads", json=valid_lead())
    assert response.status_code == 201
    assert response.json()["status"] == "saved"
    assert response.json()["id"] > 0
    with sqlite3.connect(DATABASE_PATH) as db:
        row = db.execute("SELECT name, contact, utm_source FROM leads WHERE id=?", (response.json()["id"],)).fetchone()
    assert row == ("Анна", "+7 900 123-45-67", "direct")


def test_invalid_lead_is_rejected():
    assert client.post("/api/leads", json=valid_lead(contact="x")).status_code == 422
    assert client.post("/api/leads", json=valid_lead(consent=False)).status_code == 422
    assert client.post("/api/leads", json=valid_lead(event_date="2020-01-01")).status_code == 422


def test_honeypot_is_rejected():
    assert client.post("/api/leads", json=valid_lead(website="spam.example")).status_code == 400


def test_static_and_legal_pages():
    assert client.get("/static/site.css").status_code == 200
    assert client.get("/privacy").status_code == 200
    assert client.get("/robots.txt").status_code == 200
    assert client.get("/sitemap.xml").status_code == 200

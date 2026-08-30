"""Öffentlich/Admin-Trennung: Lesezugriff frei, Schreibzugriff nur mit Session."""
import os
import subprocess
import sys
from pathlib import Path

import httpx
import pytest

WRITE_CALLS = [
    ("post", "/api/terms", {"term": "unauthorized-probe", "category": "it"}),
    ("patch", "/api/terms/1", {"enabled": False}),
    ("delete", "/api/terms/1", None),
    ("patch", "/api/sources/news", {"enabled": False}),
    ("post", "/api/collect", None),
    ("post", "/api/maintenance/cleanup", None),
    ("put", "/api/settings", {"values": {"theme": "light"}}),
]


@pytest.mark.asyncio
async def test_public_read_access_works(app_client: httpx.AsyncClient):
    for path in ("/api/health", "/api/meta", "/api/posts", "/api/stats", "/api/sources", "/api/terms"):
        r = await app_client.get(path)
        assert r.status_code == 200, f"{path} -> {r.status_code}"


@pytest.mark.asyncio
async def test_public_write_requests_are_rejected(app_client: httpx.AsyncClient):
    for method, path, body in WRITE_CALLS:
        r = await app_client.request(method.upper(), path, json=body)
        assert r.status_code == 401, f"{method.upper()} {path} -> {r.status_code} (erwartet 401)"


@pytest.mark.asyncio
async def test_login_requires_correct_credentials(app_client: httpx.AsyncClient):
    r = await app_client.post(
        "/api/auth/login", json={"username": "testadmin", "password": "falsches-passwort"}
    )
    assert r.status_code == 401

    r = await app_client.get("/api/auth/me")
    assert r.json()["authenticated"] is False

    r = await app_client.post(
        "/api/auth/login",
        json={"username": os.environ["ADMIN_USERNAME"], "password": os.environ["ADMIN_PASSWORD"]},
    )
    assert r.status_code == 200
    assert r.json()["authenticated"] is True

    r = await app_client.get("/api/auth/me")
    assert r.json()["authenticated"] is True


@pytest.mark.asyncio
async def test_authenticated_admin_write_requests_work(admin_client: httpx.AsyncClient):
    r = await admin_client.post("/api/terms", json={"term": "admin-probe-term", "category": "it"})
    assert r.status_code == 201
    term_id = r.json()["id"]

    r = await admin_client.patch(f"/api/terms/{term_id}", json={"enabled": False})
    assert r.status_code == 200
    assert r.json()["enabled"] is False

    r = await admin_client.patch("/api/sources/news", json={"interval_seconds": 200})
    assert r.status_code == 200
    assert r.json()["interval_seconds"] == 200

    r = await admin_client.put("/api/settings", json={"values": {"theme": "light"}})
    assert r.status_code == 200

    assert (await admin_client.delete(f"/api/terms/{term_id}")).status_code == 204


@pytest.mark.asyncio
async def test_logout_invalidates_admin_access(admin_client: httpx.AsyncClient):
    # admin_client ist bereits eingeloggt - ein Schreibzugriff funktioniert.
    r = await admin_client.post("/api/terms", json={"term": "pre-logout-term", "category": "it"})
    assert r.status_code == 201

    r = await admin_client.post("/api/auth/logout")
    assert r.status_code == 200
    assert r.json()["authenticated"] is False

    r = await admin_client.get("/api/auth/me")
    assert r.json()["authenticated"] is False

    # Dieselbe Session (dasselbe Cookie) darf danach nichts mehr schreiben.
    r = await admin_client.post("/api/terms", json={"term": "post-logout-term", "category": "it"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_focus_mode_uses_only_get_requests(app_client: httpx.AsyncClient):
    """Der Fokus-Modus filtert nur bereits geladene Beiträge bzw. fragt sie
    über GET /api/posts?q=... ab - genau das simuliert dieser Test: eine
    Fokus-Anfrage darf niemals eine schreibende Methode brauchen und darf
    keinerlei globalen Zustand verändern."""
    before = (await app_client.get("/api/terms")).json()

    r = await app_client.get("/api/posts", params={"q": "ransomware"})
    assert r.status_code == 200

    after = (await app_client.get("/api/terms")).json()
    assert before == after  # keine Nebenwirkung auf globale Suchbegriffe


def test_no_secrets_in_frontend_build():
    """Baut das Frontend einmal durch und prüft den Output auf das Test-
    Admin-Passwort und das Session-Secret - beide dürfen im an den Browser
    ausgelieferten Bundle niemals auftauchen, weil sie ausschließlich aus
    Server-Umgebungsvariablen kommen und nie ans Frontend übergeben werden."""
    frontend = Path(__file__).resolve().parents[2] / "frontend"
    if not (frontend / "node_modules").exists():
        pytest.skip("frontend/node_modules fehlt - npm install nicht ausgeführt")

    npm = "npm.cmd" if sys.platform == "win32" else "npm"
    result = subprocess.run(
        [npm, "run", "build"], cwd=frontend, capture_output=True, text=True, timeout=180
    )
    assert result.returncode == 0, f"Frontend-Build fehlgeschlagen:\n{result.stdout}\n{result.stderr}"

    dist = frontend / "dist"
    secrets_to_check = [os.environ["ADMIN_PASSWORD"], os.environ["SESSION_SECRET"]]
    offenders = []
    for file in dist.rglob("*"):
        if not file.is_file() or file.suffix not in {".js", ".html", ".css", ".map"}:
            continue
        text = file.read_text(encoding="utf-8", errors="ignore")
        for secret in secrets_to_check:
            if secret in text:
                offenders.append((file.name, secret))
    assert not offenders, f"Geheimnis im Frontend-Build gefunden: {offenders}"

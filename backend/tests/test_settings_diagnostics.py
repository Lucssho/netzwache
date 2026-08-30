"""Darstellungs-Einstellungen und die Diagnose-Ansicht."""
import pytest


@pytest.mark.asyncio
async def test_settings_defaults_then_persist(app_client, admin_client):
    r = await app_client.get("/api/settings")
    assert r.status_code == 200
    defaults = r.json()
    assert defaults["font_family"] == "jetbrains"
    assert defaults["font_size"] == "13"

    r = await admin_client.put(
        "/api/settings", json={"values": {"font_family": "menlo", "font_size": "15"}}
    )
    assert r.status_code == 200
    assert r.json()["font_family"] == "menlo"
    assert r.json()["font_size"] == "15"
    # unveränderte Werte bleiben als Default erhalten
    assert r.json()["density"] == "comfortable"

    # persistiert -> zweiter GET liefert denselben Stand
    r2 = await app_client.get("/api/settings")
    assert r2.json()["font_family"] == "menlo"


@pytest.mark.asyncio
async def test_settings_rejects_bad_keys(admin_client):
    r = await admin_client.put("/api/settings", json={"values": {"böse key!": "x"}})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_diagnostics_shape_and_no_secret_leak(app_client):
    r = await app_client.get("/api/diagnostics")
    assert r.status_code == 200
    d = r.json()

    assert d["database"]["ok"] is True
    assert "redis" in d and "connected" in d["redis"]
    assert isinstance(d["known_issues"], list) and len(d["known_issues"]) >= 3
    assert {i["id"] for i in d["known_issues"]} >= {
        "docker-desktop-not-running",
        "env-not-picked-up",
        "html-in-feed",
    }

    creds = d["credentials"]
    for platform in ("bluesky", "reddit", "x", "facebook"):
        assert platform in creds
        assert "configured" in creds[platform]

    # ohne .env-Werte im Testlauf muss alles unkonfiguriert sein
    assert creds["bluesky"]["configured"] is False
    assert creds["bluesky"]["app_password"] is None


@pytest.mark.asyncio
async def test_diagnostics_masks_secrets(app_client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "bluesky_handle", "sirwan.bsky.social")
    monkeypatch.setattr(settings, "bluesky_app_password", "ix4g-gdk2-ynlf-vmjp")

    r = await app_client.get("/api/diagnostics")
    creds = r.json()["credentials"]["bluesky"]
    assert creds["configured"] is True
    assert creds["app_password"] is not None
    assert "ix4g-gdk2-ynlf-vmjp" not in creds["app_password"]
    assert creds["app_password"].startswith("ix4")
    assert "•" in creds["app_password"]

    monkeypatch.setattr(settings, "bluesky_handle", "")
    monkeypatch.setattr(settings, "bluesky_app_password", "")

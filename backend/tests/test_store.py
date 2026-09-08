"""Sicherstellen, dass ein kollidierender Datensatz den restlichen Lauf nicht killt."""
import os
import time
from datetime import datetime, timezone

import pytest

from app.collectors.base import RawItem


@pytest.mark.asyncio
async def test_collision_does_not_drop_other_items(app_client, monkeypatch):
    from app.dedup import dedup
    from app.scheduler import engine

    now = datetime.now(timezone.utc)

    good_a = RawItem(platform="bluesky", external_id="uniq-a", text="Erster Beitrag über Linux", created_at=now)
    good_b = RawItem(platform="bluesky", external_id="uniq-b", text="Zweiter Beitrag über Docker", created_at=now)
    stored = await engine._store([good_a, good_b], ["linux"])
    assert len(stored) == 2

    # Gleiche externe ID erneut, aber Dedup-Cache "vergisst" sie ->
    # der DB-Unique-Index muss greifen, ohne die anderen Inserts zu verlieren.
    from app.enrich import content_hash, text_fingerprint

    collide = RawItem(platform="bluesky", external_id="uniq-a", text="Erster Beitrag über Linux", created_at=now)
    await dedup.forget(content_hash("bluesky", "uniq-a", collide.text))
    await dedup.forget(f"fp:{text_fingerprint(collide.text)}")

    fresh = RawItem(platform="bluesky", external_id="uniq-c", text="Dritter Beitrag über Kubernetes", created_at=now)
    stored2 = await engine._store([collide, fresh], ["linux"])

    ids = [p["external_id"] for p in stored2]
    assert "uniq-c" in ids, "Der gültige Eintrag muss trotz Kollision gespeichert werden"

    res = (await app_client.get("/api/posts?limit=50&q=kubernetes")).json()
    assert res["items"], "Kubernetes-Post muss über die API auffindbar sein"


@pytest.mark.asyncio
async def test_post_cap_removes_oldest_first(app_client, monkeypatch):
    """settings.max_posts ist die Zeilen-Obergrenze für SQLite (Dev/Tests) -
    wird sie überschritten, müssen die ältesten Posts (nach collected_at)
    zuerst raus, die neuesten aber erhalten bleiben. Über
    _enforce_storage_limits() aufgerufen (nicht _enforce_post_cap() direkt),
    damit auch die Dialekt-Weiche selbst mitgetestet wird - die Tests laufen
    auf SQLite, landen also hier."""
    from app.config import settings
    from app.scheduler import engine

    monkeypatch.setattr(settings, "max_posts", 2)

    now = datetime.now(timezone.utc)
    items = [
        RawItem(platform="bluesky", external_id="cap-old", text="Ältester Beitrag über Kubernetes", created_at=now),
        RawItem(platform="bluesky", external_id="cap-mid", text="Mittlerer Beitrag über Kubernetes", created_at=now),
        RawItem(platform="bluesky", external_id="cap-new", text="Neuester Beitrag über Kubernetes", created_at=now),
    ]
    for it in items:
        stored = await engine._store([it], ["kubernetes"])
        assert stored, f"{it.external_id} musste gespeichert werden"
        await engine._enforce_storage_limits()

    res = (await app_client.get("/api/posts?limit=50&q=kubernetes")).json()
    remaining = {p["external_id"] for p in res["items"]}
    assert len(remaining) == 2, "Obergrenze muss eingehalten werden"
    assert remaining == {"cap-mid", "cap-new"}, "die ältesten Posts müssen zuerst entfernt werden"


@pytest.mark.asyncio
async def test_storage_limits_use_post_cap_on_sqlite(app_client):
    """_enforce_storage_limits() muss auf SQLite (der Dialekt, auf dem die
    Testsuite läuft) auf die Zeilen-Obergrenze ausweichen, nicht auf die
    Postgres-spezifische Größenprüfung (die pg_total_relation_size nutzt,
    was es unter SQLite gar nicht gibt)."""
    from app.db import engine as db_engine
    from app.scheduler import engine

    assert db_engine.dialect.name == "sqlite", "Testsuite läuft laut conftest.py auf SQLite"
    # Darf nicht crashen (pg_total_relation_size existiert unter SQLite nicht) -
    # wäre _enforce_size_cap() fälschlich aufgerufen worden, würde das hier auffliegen.
    await engine._enforce_storage_limits()


@pytest.mark.skipif(
    os.environ.get("DATABASE_URL", "").startswith("sqlite"),
    reason="pg_total_relation_size gibt es nur unter Postgres",
)
@pytest.mark.asyncio
async def test_enforce_size_cap_removes_oldest_chunk_on_postgres(app_client, monkeypatch):
    """Nur relevant, wenn die Tests direkt gegen Postgres laufen (DATABASE_URL
    entsprechend gesetzt) - die Standard-Testsuite läuft auf SQLite und
    überspringt das hier. Live gegen die echte Postgres-Instanz manuell
    verifiziert (siehe Sitzungsprotokoll)."""
    from app.config import settings
    from app.scheduler import engine

    now = datetime.now(timezone.utc)
    items = [
        RawItem(
            platform="bluesky",
            external_id=f"size-cap-{i}",
            text="X" * 2000 + f" Beitrag Nummer {i} über Kubernetes",
            created_at=now,
        )
        for i in range(20)
    ]
    stored = await engine._store(items, ["kubernetes"])
    assert len(stored) == 20

    # Limit absichtlich winzig setzen, damit die aktuelle Tabellengröße
    # garantiert darüber liegt, unabhängig davon, wie groß sie schon ist.
    monkeypatch.setattr(settings, "max_posts_size_gb", 0.000001)
    monkeypatch.setattr(settings, "posts_trim_chunk_mb", 0.01)

    await engine._enforce_size_cap()

    res = (await app_client.get("/api/posts?limit=50&q=kubernetes")).json()
    remaining_ids = {p["external_id"] for p in res["items"]}
    oldest = "size-cap-0"
    newest = "size-cap-19"
    assert oldest not in remaining_ids, "der älteste Post muss zuerst entfernt werden"
    assert newest in remaining_ids, "der neueste Post muss erhalten bleiben"


@pytest.mark.asyncio
async def test_retention_cleanup_runs_automatically_on_first_tick(app_client, monkeypatch):
    """_maybe_cleanup lief früher nur über den manuellen Admin-Endpunkt. Jetzt
    muss sie beim allerersten Tick sofort laufen (self._last_cleanup ist noch
    None) und retention_days respektieren."""
    from app.config import settings
    from app.scheduler import engine

    monkeypatch.setattr(settings, "retention_days", 0)
    engine._last_cleanup = None  # Zustand "noch nie gelaufen" unabhängig von anderen Tests erzwingen

    now = datetime.now(timezone.utc)
    item = RawItem(platform="reddit", external_id="cleanup-old", text="Alter Beitrag über Phishing", created_at=now)
    stored = await engine._store([item], ["phishing"])
    assert stored, "Testdaten müssen zuerst gespeichert werden"

    await engine._maybe_cleanup(time.monotonic())

    res = (await app_client.get("/api/posts?limit=50&q=phishing")).json()
    ids = {p["external_id"] for p in res["items"]}
    assert "cleanup-old" not in ids, "retention_days=0 muss den Post beim ersten automatischen Lauf entfernen"


@pytest.mark.asyncio
async def test_retention_cleanup_respects_interval(app_client, monkeypatch):
    """Innerhalb von cleanup_interval_seconds darf kein zweiter Durchlauf
    passieren - sonst würde jeder Tick die DB abfragen, obwohl retention_days
    sich nicht geändert hat."""
    from app.config import settings
    from app.scheduler import engine

    monkeypatch.setattr(settings, "retention_days", 0)
    monkeypatch.setattr(settings, "cleanup_interval_seconds", 999_999)

    now = datetime.now(timezone.utc)
    first = RawItem(platform="reddit", external_id="cleanup-first", text="Erster Beitrag über Malware", created_at=now)
    await engine._store([first], ["malware"])

    t0 = time.monotonic()
    engine._last_cleanup = None
    await engine._maybe_cleanup(t0)  # läuft (erster Aufruf) und entfernt cleanup-first

    second = RawItem(platform="reddit", external_id="cleanup-second", text="Zweiter Beitrag über Malware", created_at=now)
    await engine._store([second], ["malware"])
    await engine._maybe_cleanup(t0 + 1)  # weit innerhalb des Intervalls -> darf nichts löschen

    res = (await app_client.get("/api/posts?limit=50&q=malware")).json()
    ids = {p["external_id"] for p in res["items"]}
    assert "cleanup-first" not in ids, "der erste Durchlauf muss den alten Post entfernt haben"
    assert "cleanup-second" in ids, "innerhalb des Intervalls darf kein zweiter Durchlauf passieren"

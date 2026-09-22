"""Speichern: Kollisionen dürfen den Lauf nicht killen, und die einzige
automatische Löschregel für posts ist die Größenobergrenze (Postgres) -
kein Alter, keine Zeilenzahl. Siehe scheduler.py::_enforce_storage_limits."""
import os
from datetime import datetime, timedelta, timezone

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


@pytest.mark.skipif(
    not os.environ.get("DATABASE_URL", "").startswith("sqlite"),
    reason="testet die SQLite-Dialekt-Weiche in _enforce_storage_limits() speziell",
)
@pytest.mark.asyncio
async def test_storage_limits_are_a_noop_on_sqlite(app_client):
    """Unter SQLite (Testsuite) gibt es keine automatische Löschregel mehr -
    weder nach Alter noch nach Zeilenzahl (beide wurden entfernt). Ein sehr
    alter Post muss unangetastet bleiben, auch nach _enforce_storage_limits()."""
    from app.db import engine as db_engine
    from app.scheduler import engine

    assert db_engine.dialect.name == "sqlite", "Testsuite läuft laut conftest.py auf SQLite"

    ancient = RawItem(
        platform="reddit",
        external_id="noop-ancient",
        text="Uralter Beitrag über Kubernetes",
        created_at=datetime.now(timezone.utc) - timedelta(days=3650),
    )
    stored = await engine._store([ancient], ["kubernetes"])
    assert stored, "Testdaten müssen zuerst gespeichert werden"

    await engine._enforce_storage_limits()

    res = (await app_client.get("/api/posts?limit=50&q=kubernetes")).json()
    assert "noop-ancient" in {p["external_id"] for p in res["items"]}, (
        "kein Alter/keine Zeilenzahl darf einen Post automatisch entfernen"
    )


@pytest.mark.skipif(
    os.environ.get("DATABASE_URL", "").startswith("sqlite"),
    reason="pg_total_relation_size gibt es nur unter Postgres",
)
@pytest.mark.asyncio
async def test_enforce_size_cap_removes_oldest_chunk_on_postgres(app_client, monkeypatch, clean_posts_table):
    """Nur relevant, wenn die Tests direkt gegen Postgres laufen (DATABASE_URL
    entsprechend gesetzt) - die Standard-Testsuite läuft auf SQLite und
    überspringt das hier. Live gegen die echte Postgres-Instanz manuell
    verifiziert (siehe Sitzungsprotokoll).

    clean_posts_table: _enforce_size_cap() löscht global die ältesten Posts
    der ganzen Tabelle, nicht nur die dieses Tests - ohne eine leere
    Ausgangslage würden liegengebliebene (ältere) Posts anderer Tests im
    selben Testlauf zuerst gelöscht statt "size-cap-0", und der Test würde
    fälschlich fehlschlagen."""
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


@pytest.mark.skipif(
    os.environ.get("DATABASE_URL", "").startswith("sqlite"),
    reason="_enforce_size_cap ist Postgres-spezifisch",
)
@pytest.mark.asyncio
async def test_size_cap_ignores_age_and_row_count_below_the_limit(app_client, monkeypatch, clean_posts_table):
    """Solange die Tabelle unter dem Größenlimit bleibt, darf NICHTS gelöscht
    werden - auch ein sehr alter Post oder eine hohe Zeilenzahl allein sind
    kein Löschgrund mehr (frühere RETENTION_DAYS/MAX_POSTS-Regeln entfernt)."""
    from app.config import settings
    from app.scheduler import engine

    ancient = RawItem(
        platform="reddit",
        external_id="pg-noop-ancient",
        text="Uralter Beitrag über Kubernetes",
        created_at=datetime.now(timezone.utc) - timedelta(days=3650),
    )
    stored = await engine._store([ancient], ["kubernetes"])
    assert stored

    monkeypatch.setattr(settings, "max_posts_size_gb", 1000.0)  # weit über der Tabellengröße
    await engine._enforce_size_cap()

    res = (await app_client.get("/api/posts?limit=50&q=kubernetes")).json()
    assert "pg-noop-ancient" in {p["external_id"] for p in res["items"]}, (
        "unterhalb des Größenlimits darf Alter allein kein Löschgrund sein"
    )

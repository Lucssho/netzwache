"""Ein Beitrag, der NICHT in der DB gelandet ist, darf danach nicht als "schon gesehen" gelten.

Hintergrund: Engine._store() markiert Beiträge in der Dedup-Schicht (Redis) schon
VOR dem DB-Schreiben. Früher gab ein fehlgeschlagener Insert nur den Inhalts-Hash
frei, nicht den Text-Fingerabdruck - der Beitrag wurde danach für die ganze TTL
(14 Tage) still verworfen. Diese Tests decken jeden Fehlerpfad ab.
"""
from datetime import datetime, timezone

import pytest

from app.collectors.base import RawItem
from app.dedup import dedup
from app.enrich import content_hash, normalize, text_fingerprint


def _keys(item: RawItem) -> tuple[str, str]:
    """Dieselben Schlüssel wie in Engine._store()."""
    text = normalize(item.text)
    return (
        content_hash(item.platform, item.external_id, text),
        f"fp:{text_fingerprint(f'{item.title} {text}')}",
    )


def _item(ext_id: str, text: str) -> RawItem:
    return RawItem(platform="bluesky", external_id=ext_id, text=text, created_at=datetime.now(timezone.utc))


@pytest.mark.asyncio
async def test_failed_insert_is_retried_on_next_run(app_client, monkeypatch):
    from app import scheduler
    from app.scheduler import engine

    item = _item("rel-fail-insert", "Erster Versuch scheitert beim Schreiben, Thema Linux")

    def boom(*args, **kwargs):
        raise RuntimeError("simulierter Fehler beim Schreiben der Tag-Zeile")

    with monkeypatch.context() as m:
        m.setattr(scheduler, "PostTag", boom)
        stored = await engine._store([item], ["linux"])
    assert stored == [], "der Insert schlug fehl - nichts darf gespeichert sein"

    h, fp = _keys(item)
    assert await dedup.seen(h) is False, "Inhalts-Hash muss wieder frei sein"
    await dedup.forget(h)
    assert await dedup.seen(fp) is False, "Text-Fingerabdruck muss ebenfalls frei sein (früher: stehengeblieben)"
    await dedup.forget(fp)

    retried = await engine._store([item], ["linux"])
    assert [p["external_id"] for p in retried] == ["rel-fail-insert"], "beim nächsten Lauf muss der Beitrag gespeichert werden"


@pytest.mark.asyncio
async def test_true_duplicate_stays_marked(app_client):
    """Liegt der Beitrag schon in der DB, ist er ein echtes Duplikat - seine
    Markierung soll bleiben, sonst würde er bei jedem Lauf erneut versucht."""
    from app.scheduler import engine

    item = _item("rel-dup", "Dieser Beitrag liegt bereits in der Datenbank")
    assert len(await engine._store([item], [])) == 1

    h, fp = _keys(item)
    # Redis-Gedächtnis ist weg (z.B. Neustart) - die DB erkennt das Duplikat trotzdem.
    await dedup.forget_many([h, fp])
    assert await engine._store([item], []) == [], "echtes Duplikat wird nicht noch einmal gespeichert"

    assert await dedup.seen(h) is True, "Hash bleibt markiert, damit der Beitrag nicht ständig neu versucht wird"
    assert await dedup.seen(fp) is True, "Fingerabdruck bleibt ebenfalls markiert"


@pytest.mark.asyncio
async def test_commit_failure_releases_all_keys(app_client, monkeypatch):
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.scheduler import engine

    a = _item("rel-commit-a", "Erster Beitrag, dessen Commit scheitert")
    b = _item("rel-commit-b", "Zweiter Beitrag, dessen Commit ebenfalls scheitert")

    real_commit = AsyncSession.commit
    calls = {"n": 0}

    async def flaky_commit(self):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("simulierter Commit-Fehler")
        return await real_commit(self)

    monkeypatch.setattr(AsyncSession, "commit", flaky_commit)
    with pytest.raises(RuntimeError, match="Commit-Fehler"):
        await engine._store([a, b], [])

    for it in (a, b):
        h, fp = _keys(it)
        assert await dedup.seen(h) is False and await dedup.seen(fp) is False, (
            "der Commit wurde zurückgerollt - beide Schlüssel jedes Beitrags müssen frei sein"
        )
        await dedup.forget_many([h, fp])

    # Postgres rollt den fehlgeschlagenen Commit vollständig zurück (Beiträge
    # werden jetzt neu gespeichert); SQLite (Testdatenbank) behält die Zeilen
    # trotz Fehler (bekannte pysqlite-Eigenheit bei Savepoints) - dann werden
    # sie korrekt als Duplikat erkannt. Entscheidend ist in beiden Fällen: der
    # Lauf wirft nicht, und beide Beiträge sind danach in der DB.
    await engine._store([a, b], [])
    res = (await app_client.get("/api/posts?limit=50&q=Commit")).json()
    present = {p["external_id"] for p in res["items"]}
    assert {"rel-commit-a", "rel-commit-b"} <= present, "kein Beitrag darf durch den Commit-Fehler verloren gehen"


@pytest.mark.asyncio
async def test_db_unavailable_releases_keys(app_client, monkeypatch):
    """DB nicht erreichbar (z.B. beim Neustart) - der komplette Stapel darf nicht verloren gehen."""
    from app import scheduler
    from app.scheduler import engine

    item = _item("rel-db-down", "Beitrag, während die Datenbank gerade nicht erreichbar ist")

    class DownSession:
        async def __aenter__(self):
            raise ConnectionError("simulierte: Datenbank nicht erreichbar")

        async def __aexit__(self, *exc):
            return False

    with monkeypatch.context() as m:
        m.setattr(scheduler, "SessionLocal", lambda: DownSession())
        with pytest.raises(ConnectionError):
            await engine._store([item], [])

    h, fp = _keys(item)
    assert await dedup.seen(h) is False and await dedup.seen(fp) is False
    await dedup.forget_many([h, fp])

    assert len(await engine._store([item], [])) == 1, "nach der DB-Störung muss der Beitrag normal ankommen"


@pytest.mark.asyncio
async def test_successful_store_keeps_keys_marked(app_client):
    """Gegenprobe: ein erfolgreich gespeicherter Beitrag bleibt markiert (sonst wäre Dedup wirkungslos)."""
    from app.scheduler import engine

    item = _item("rel-ok", "Ganz normaler, erfolgreich gespeicherter Beitrag")
    assert len(await engine._store([item], [])) == 1
    h, fp = _keys(item)
    assert await dedup.seen(h) is True
    assert await dedup.seen(fp) is True
    assert await engine._store([item], []) == [], "zweiter Durchlauf desselben Beitrags wird als Duplikat verworfen"


@pytest.mark.asyncio
async def test_forget_many_frees_every_key():
    from app.dedup import Dedup

    d = Dedup()  # reiner Memory-Modus, kein Redis
    assert await d.seen("a") is False and await d.seen("b") is False
    assert await d.seen("a") is True
    await d.forget_many(["a", "b"])
    assert await d.seen("a") is False and await d.seen("b") is False
    await d.forget_many([])  # leere Liste darf nicht crashen

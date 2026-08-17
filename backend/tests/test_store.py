"""Sicherstellen, dass ein kollidierender Datensatz den restlichen Lauf nicht killt."""
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

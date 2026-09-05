"""Normalisierte Kategorien/Tags/CVEs (post_categories, post_tags,
post_cves): werden beim Speichern korrekt mitgeschrieben, filtern per JOIN
statt JSON-Array-Suche, und lassen sich für Bestandsdaten per
migrate_normalize.py nachtragen."""
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.collectors.base import RawItem


@pytest.mark.asyncio
async def test_store_writes_normalized_categories_tags_and_cves(app_client):
    from app.db import SessionLocal
    from app.models import Category, PostCategory, PostCve, PostTag
    from app.scheduler import engine

    now = datetime.now(timezone.utc)
    item = RawItem(
        platform="reddit",
        external_id="norm-1",
        text="Neue Linux-Kernel-Version behebt CVE-2026-99001 - eine kritische Sicherheitslücke",
        source="r/linux",
        created_at=now,
    )
    stored = await engine._store([item], ["linux", "CVE"])
    assert stored
    post_id = stored[0]["id"]
    assert "cybersecurity" in stored[0]["categories"]
    assert set(stored[0]["matched_terms"]) >= {"linux", "CVE"}
    assert "CVE-2026-99001" in stored[0]["cve_ids"]

    async with SessionLocal() as s:
        cat_rows = (
            await s.execute(
                select(Category.name)
                .join(PostCategory, PostCategory.category_id == Category.id)
                .where(PostCategory.post_id == post_id)
            )
        ).scalars().all()
        tag_rows = (
            await s.execute(select(PostTag.tag).where(PostTag.post_id == post_id))
        ).scalars().all()
        cve_rows = (
            await s.execute(select(PostCve.cve).where(PostCve.post_id == post_id))
        ).scalars().all()

    assert "cybersecurity" in cat_rows, "post_categories muss dieselben Kategorien wie die JSON-Spalte enthalten"
    assert set(tag_rows) == set(stored[0]["matched_terms"]), "post_tags muss zu matched_terms passen"
    assert set(cve_rows) == set(stored[0]["cve_ids"]), "post_cves muss zu cve_ids passen"


@pytest.mark.asyncio
async def test_posts_filter_by_category_tag_and_cve_via_join(app_client):
    from app.scheduler import engine

    now = datetime.now(timezone.utc)
    items = [
        RawItem(
            platform="reddit",
            external_id="norm-tag-a",
            text="Kubernetes Cluster abgesichert gegen zero-day Exploit CVE-2026-99002",
            source="r/kubernetes",
            created_at=now,
        ),
        RawItem(
            platform="googlenews",
            external_id="norm-tag-b",
            text="Linux Kernel 8.0 bringt neue Treiber",
            source="heise",
            created_at=now,
        ),
    ]
    stored = await engine._store(items, ["linux", "zero-day"])
    assert len(stored) == 2

    # tag-Filter: nur der zero-day-Post
    r = (await app_client.get("/api/posts?tag=zero-day")).json()
    ext_ids = {p["external_id"] for p in r["items"]}
    assert "norm-tag-a" in ext_ids
    assert "norm-tag-b" not in ext_ids

    # cve-Filter (Groß-/Kleinschreibung darf keine Rolle spielen)
    r_cve = (await app_client.get("/api/posts?cve=cve-2026-99002")).json()
    assert r_cve["total"] == 1
    assert r_cve["items"][0]["external_id"] == "norm-tag-a"

    # category-Filter kombiniert mit platform
    r2 = (await app_client.get("/api/posts?category=cybersecurity&platform=reddit&tag=zero-day")).json()
    assert r2["total"] == len(r2["items"]) == 1
    assert r2["items"][0]["external_id"] == "norm-tag-a"

    # unbekannter Tag/CVE -> keine Treffer, kein Fehler
    r3 = (await app_client.get("/api/posts?tag=does-not-exist-tag")).json()
    assert r3["total"] == 0
    assert r3["items"] == []
    r4 = (await app_client.get("/api/posts?cve=CVE-1999-00000")).json()
    assert r4["total"] == 0


@pytest.mark.asyncio
async def test_stats_by_category_and_top_cves_use_normalized_joins(app_client):
    from app.scheduler import engine

    now = datetime.now(timezone.utc)
    marker_items = [
        RawItem(
            platform="reddit",
            external_id=f"norm-stats-{i}",
            text=f"ransomware vorfall statstest{i} CVE-2026-99100",
            created_at=now,
        )
        for i in range(5)
    ]
    stored = await engine._store(marker_items, [])
    assert len(stored) == 5

    stats = (await app_client.get("/api/stats")).json()
    # mindestens die 5 gerade gespeicherten - andere Tests tragen ggf. auch cybersecurity-Posts bei
    assert stats["by_category"]["cybersecurity"] >= 5
    cve_counts = dict(stats["top_cves"])
    assert cve_counts.get("CVE-2026-99100", 0) >= 5


@pytest.mark.asyncio
async def test_migrate_normalize_backfills_legacy_posts_idempotently(app_client):
    """Simuliert einen "alten" Post, der vor der Normalisierung gespeichert
    wurde: categories/matched_terms/cve_ids nur als JSON, keine
    post_categories/post_tags/post_cves-Zeilen. migrate_normalize.run() muss
    das nachtragen - und beim zweiten Lauf keine Duplikate erzeugen bzw.
    nicht crashen."""
    from app.db import SessionLocal
    from app.enrich import enrich, normalize
    from app.migrate_normalize import run as migrate_run
    from app.models import Category, Post, PostCategory, PostCve, PostTag

    text = normalize("Alter Bestandspost über eine Ransomware-Attacke CVE-2026-99200 und Linux-Server")
    meta = enrich(text, "", "", ["linux"])
    assert meta["cve_ids"], "Testtext muss eine erkennbare CVE enthalten"
    async with SessionLocal() as s:
        legacy = Post(
            platform="news",
            source="legacy-source",
            external_id="legacy-migrate-1",
            content_hash="legacy-hash-migrate-1",
            text=text,
            created_at=datetime.now(timezone.utc),
            collected_at=datetime.now(timezone.utc),
            **meta,
        )
        s.add(legacy)
        await s.commit()
        await s.refresh(legacy)
        post_id = legacy.id

    async def normalized_state():
        async with SessionLocal() as s:
            cats = (
                await s.execute(
                    select(Category.name)
                    .join(PostCategory, PostCategory.category_id == Category.id)
                    .where(PostCategory.post_id == post_id)
                )
            ).scalars().all()
            tags = (
                await s.execute(select(PostTag.tag).where(PostTag.post_id == post_id))
            ).scalars().all()
            cves = (
                await s.execute(select(PostCve.cve).where(PostCve.post_id == post_id))
            ).scalars().all()
            return set(cats), set(tags), set(cves)

    before_cats, before_tags, before_cves = await normalized_state()
    assert before_cats == set(), "vor der Migration darf der Legacy-Post noch keine post_categories haben"
    assert before_tags == set()
    assert before_cves == set()

    first_cats, first_tags, first_cves = await migrate_run()
    assert first_cats > 0 and first_tags > 0 and first_cves > 0

    after_cats, after_tags, after_cves = await normalized_state()
    assert after_cats == set(meta["categories"])
    assert after_tags == set(meta["matched_terms"])
    assert after_cves == set(meta["cve_ids"])

    # zweiter Lauf: idempotent, keine Duplikate/Fehler - und meldet auch
    # korrekt 0 tatsächlich neu eingefügte Zeilen (nicht die Anzahl der
    # versuchten, per ON CONFLICT übersprungenen Inserts).
    second_cats, second_tags, second_cves = await migrate_run()
    assert (second_cats, second_tags, second_cves) == (0, 0, 0)

    after_cats_2, after_tags_2, after_cves_2 = await normalized_state()
    assert after_cats_2 == after_cats
    assert after_tags_2 == after_tags
    assert after_cves_2 == after_cves

"""Regressionstests für das Datenformat v2 (siehe README, Abschnitt
"Version 1 vs. Version 2"). Deckt genau die Anforderungen aus der
Aufgabenstellung ab: Bestandsdaten (Version 1) bleiben unangetastet und
lesbar, neu gesammelte Beiträge (Version 2) bekommen die neuen Felder
ehrlich befüllt, Engagement unterscheidet fehlend von echt Null, und
raw_payload ist nie mit Zugangsdaten verschmutzt oder unbegrenzt groß."""
from __future__ import annotations

import os
from datetime import datetime, timezone

import httpx
import pytest

from app.collectors.base import RawItem
from app.collectors.bluesky import BlueskyCollector
from app.collectors.facebook import FacebookCollector
from app.collectors.googlenews import GoogleNewsCollector
from app.collectors.news import NewsCollector
from app.collectors.reddit import RedditCollector
from app.payload import sanitize_raw_payload


def make_client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


# ---------------------------------------------------------------- 1 + 13
@pytest.mark.asyncio
async def test_legacy_post_reads_as_version_1_and_keeps_existing_fields(app_client):
    """Ein Bestandspost (wie vor dieser Änderung gespeichert - kein
    data_version/content_status gesetzt) muss weiterhin über die API lesbar
    sein, mit data_version=1 und content_status="legacy" statt rohem NULL,
    UND alle bisherigen Felder müssen unverändert vorhanden sein."""
    from app.db import SessionLocal
    from app.models import Post

    now = datetime.now(timezone.utc)
    async with SessionLocal() as s:
        legacy = Post(
            platform="news",
            source="legacy-source",
            external_id="v2-legacy-1",
            content_hash="v2-legacy-hash-1",
            title="Alter Titel",
            text="Alter Bestandstext, lange vor der Erweiterung gespeichert.",
            url="https://example.org/legacy",
            created_at=now,
            collected_at=now,
        )
        s.add(legacy)
        await s.commit()
        await s.refresh(legacy)
        post_id = legacy.id

    res = await app_client.get(f"/api/posts/{post_id}")
    assert res.status_code == 200
    d = res.json()

    # neue Felder: sauberer Fallback statt rohem NULL
    assert d["data_version"] == 1
    assert d["content_status"] == "legacy"
    assert d["content_type"] is None
    assert d["summary"] is None
    assert d["content_full"] is None
    assert d["canonical_url"] is None
    assert d["collector_mode"] is None
    assert d["engagement_collected_at"] is None
    assert d["media"] == []

    # bisherige Felder unverändert vorhanden und unangetastet
    assert d["platform"] == "news"
    assert d["source"] == "legacy-source"
    assert d["title"] == "Alter Titel"
    assert d["text"] == "Alter Bestandstext, lange vor der Erweiterung gespeichert."
    assert d["url"] == "https://example.org/legacy"
    assert d["categories"] == []
    assert d["engagement"] == {}


# --------------------------------------------------------------------- 2
@pytest.mark.asyncio
async def test_newly_stored_post_gets_data_version_2(app_client):
    from app.scheduler import engine

    now = datetime.now(timezone.utc)
    item = RawItem(
        platform="bluesky",
        external_id="v2-new-1",
        text="Ein frisch gesammelter Beitrag über Linux",
        created_at=now,
    )
    stored = await engine._store([item], ["linux"])
    assert stored
    assert stored[0]["data_version"] == 2
    assert stored[0]["content_status"] == "full"  # RawItem-Default, siehe base.py


# --------------------------------------------------------------- 3, 4, 6
@pytest.mark.asyncio
async def test_bluesky_full_post_preserves_complete_text():
    payload = {
        "posts": [
            {
                "uri": "at://did:plc:x/app.bsky.feed.post/v2a",
                "cid": "bafyv2a",
                "author": {"handle": "tester.bsky.social", "displayName": "Tester"},
                "record": {"text": "Vollständiger Bluesky-Text ohne Kürzung", "createdAt": "2026-08-13T10:00:00.000Z"},
                "likeCount": 4,
            }
        ]
    }

    async with make_client(lambda r: httpx.Response(200, json=payload)) as client:
        items = await BlueskyCollector(client).fetch(["linux"])

    it = items[0]
    assert it.content_type == "post"
    assert it.content_status == "full"
    assert it.content_full == "Vollständiger Bluesky-Text ohne Kürzung"
    assert it.content_full == it.text, "content_full darf sich bei 'full' nicht vom Anzeigetext unterscheiden"


@pytest.mark.asyncio
async def test_reddit_self_post_preserves_complete_selftext():
    payload = {
        "data": {
            "children": [
                {
                    "data": {
                        "name": "t3_v2self",
                        "id": "v2self",
                        "title": "Ein Selbstbeitrag",
                        "selftext": "Das ist der vollständige Selbstbeitrags-Text.",
                        "is_self": True,
                        "author": "someone",
                        "subreddit": "linux",
                        "permalink": "/r/linux/comments/v2self/x/",
                        "created_utc": 1786000000,
                    }
                }
            ]
        }
    }

    async with make_client(lambda r: httpx.Response(200, json=payload)) as client:
        items = await RedditCollector(client).fetch(["linux"])

    it = items[0]
    assert it.content_type == "self_post"
    assert it.content_status == "full"
    assert it.content_full == "Das ist der vollständige Selbstbeitrags-Text."


@pytest.mark.asyncio
async def test_reddit_link_post_does_not_claim_external_article_was_collected():
    """Ein Link-Post hat keinen eigenen Volltext - das externe Ziel wird
    nicht nachgeladen. content_status darf hier NIE "full" sein, und die
    externe URL muss getrennt vom Reddit-eigenen Permalink stehen."""
    payload = {
        "data": {
            "children": [
                {
                    "data": {
                        "name": "t3_v2link",
                        "id": "v2link",
                        "title": "Schau dir das an",
                        "selftext": "",
                        "is_self": False,
                        "url": "https://example.org/external-article",
                        "author": "someone",
                        "subreddit": "linux",
                        "permalink": "/r/linux/comments/v2link/x/",
                        "created_utc": 1786000000,
                    }
                }
            ]
        }
    }

    async with make_client(lambda r: httpx.Response(200, json=payload)) as client:
        items = await RedditCollector(client).fetch(["linux"])

    it = items[0]
    assert it.content_type == "link_post"
    assert it.content_status != "full"
    assert it.content_status == "title_only"
    assert it.content_full in (None, "")
    assert it.canonical_url == "https://example.org/external-article"
    assert it.url != it.canonical_url, "Reddit-Permalink und externes Ziel müssen getrennt bleiben"


# --------------------------------------------------------------------- 5
@pytest.mark.asyncio
async def test_rss_summary_is_not_labeled_as_full_article():
    rss = """<?xml version="1.0"?>
<rss version="2.0"><channel>
<item>
  <title>Kurzer Titel</title>
  <description>Nur eine kurze Zusammenfassung, nicht der ganze Artikeltext.</description>
  <link>https://example.org/a1</link>
  <pubDate>Wed, 13 Aug 2026 08:00:00 GMT</pubDate>
  <guid>a1</guid>
</item>
</channel></rss>"""

    async with make_client(lambda r: httpx.Response(200, content=rss.encode())) as client:
        items = await NewsCollector(client).fetch([])

    it = items[0]
    assert it.content_status == "summary"
    assert it.content_status != "full"
    assert it.content_full in (None, ""), "eine RSS-Zusammenfassung darf nie als Volltext ausgegeben werden"
    assert it.summary == "Nur eine kurze Zusammenfassung, nicht der ganze Artikeltext."


# --------------------------------------------------------------------- 6
@pytest.mark.asyncio
async def test_googlenews_title_only_entry_is_represented_honestly():
    """Ein Google-News-Eintrag ganz ohne Beschreibung darf nicht so
    aussehen, als hätten wir mehr als den Titel eingesammelt."""
    rss = """<?xml version="1.0"?>
<rss version="2.0"><channel>
<item>
  <title>Nur ein Titel - heise online</title>
  <link>https://news.google.com/rss/articles/xyz</link>
  <pubDate>Wed, 13 Aug 2026 08:00:00 GMT</pubDate>
  <guid>gn-titleonly</guid>
  <source url="https://www.heise.de">heise online</source>
</item>
</channel></rss>"""

    async with make_client(lambda r: httpx.Response(200, content=rss.encode())) as client:
        items = await GoogleNewsCollector(client).fetch(["cve"])

    it = items[0]
    assert it.content_status == "title_only"
    assert it.summary == ""
    assert it.content_full in (None, "")


# --------------------------------------------------------------------- 7
@pytest.mark.asyncio
async def test_facebook_engagement_distinguishes_missing_from_zero(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "facebook_page_token", "TOK")
    monkeypatch.setattr(settings, "facebook_page_ids", "1,2")

    def handler(request: httpx.Request) -> httpx.Response:
        page_id = str(request.url).rsplit("/", 2)[-2]
        if page_id == "1":
            # shares mit explizit 0 - ein ECHTER Nullwert
            data = [{"id": "1_1", "message": "Post A", "created_time": "2026-08-13T07:00:00+0000",
                     "permalink_url": "https://facebook.com/1_1", "shares": {"count": 0}}]
        else:
            # shares-Objekt fehlt komplett - Facebook liefert das oft so
            data = [{"id": "2_1", "message": "Post B", "created_time": "2026-08-13T07:00:00+0000",
                     "permalink_url": "https://facebook.com/2_1"}]
        return httpx.Response(200, json={"data": data})

    async with make_client(handler) as client:
        items = await FacebookCollector(client).fetch([])

    by_id = {i.external_id: i for i in items}
    assert by_id["fb:1_1"].engagement.get("shares") == 0, "ein echter Nullwert muss als 0 erhalten bleiben"
    assert "shares" not in by_id["fb:2_1"].engagement, (
        "fehlende Engagement-Daten dürfen nicht stillschweigend zu 0 werden"
    )

    monkeypatch.setattr(settings, "facebook_page_token", "")
    monkeypatch.setattr(settings, "facebook_page_ids", "")


# --------------------------------------------------------------------- 8
@pytest.mark.asyncio
async def test_engagement_collected_at_set_only_when_engagement_present(app_client):
    from app.scheduler import engine

    now = datetime.now(timezone.utc)
    with_engagement = RawItem(
        platform="bluesky", external_id="v2-eng-1", text="Beitrag mit Engagement über Kubernetes",
        engagement={"likes": 3}, created_at=now,
    )
    without_engagement = RawItem(
        platform="news", external_id="v2-eng-2", text="Beitrag ohne Engagement über Kubernetes",
        created_at=now,
    )
    stored = await engine._store([with_engagement, without_engagement], ["kubernetes"])
    by_id = {p["external_id"]: p for p in stored}

    assert by_id["v2-eng-1"]["engagement_collected_at"] is not None
    assert by_id["v2-eng-2"]["engagement_collected_at"] is None


# --------------------------------------------------------------------- 9
def test_raw_payload_sanitizer_strips_credentials():
    dirty = {
        "id": "abc123",
        "text": "harmloser Inhalt",
        "access_token": "SUPER-SECRET-TOKEN",
        "password": "hunter2",
        "nested": {"session_cookie": "abc", "authorization": "Bearer xyz", "keep_me": "ok"},
    }
    clean = sanitize_raw_payload(dirty)
    assert "access_token" not in clean
    assert "password" not in clean
    assert "session_cookie" not in clean["nested"]
    assert "authorization" not in clean["nested"]
    assert clean["nested"]["keep_me"] == "ok"
    assert clean["text"] == "harmloser Inhalt"


# -------------------------------------------------------------------- 10
def test_raw_payload_sanitizer_truncates_oversized_payload():
    huge = {"id": "big1", "text": "x" * 200_000}
    clean = sanitize_raw_payload(huge, max_bytes=2_000)
    import json

    assert len(json.dumps(clean, ensure_ascii=False).encode("utf-8")) <= 2_000 + 200  # kleine Toleranz für Marker-Felder
    assert clean.get("_truncated") is True, "eine gekürzte Nutzlast muss klar als solche markiert sein"


# -------------------------------------------------------------------- 11
@pytest.mark.skipif(
    not os.environ.get("DATABASE_URL", "").startswith("postgresql"),
    reason="Postgres-Schema-Migration lässt sich nur gegen echtes Postgres sinnvoll testen",
)
@pytest.mark.asyncio
async def test_postgres_schema_init_is_idempotent():
    """init_db() muss beliebig oft ohne Fehler laufen - insbesondere nach
    dem Wechsel der search_vector-Definition und beim Nachziehen der
    Datenformat-v2-Spalten auf eine schon bestehende Tabelle."""
    from app.db import init_db

    await init_db()
    await init_db()  # zweiter Lauf darf nicht crashen und nichts doppelt anlegen


# -------------------------------------------------------------------- 12
@pytest.mark.asyncio
async def test_sqlite_create_all_includes_v2_columns_from_the_start(app_client):
    """Auf SQLite (Dev/Tests) gibt es keine ALTER-TABLE-Migration - die
    v2-Spalten müssen stattdessen schon über create_all() aus dem Modell
    entstehen. Ein frisch gespeicherter Post muss sie direkt nutzen können."""
    from app.db import engine as db_engine

    assert db_engine.dialect.name == "sqlite"
    res = await app_client.get("/api/posts?limit=1")
    assert res.status_code == 200  # würde bei fehlender Spalte mit einem DB-Fehler crashen


# -------------------------------------------------------------------- 14
@pytest.mark.asyncio
async def test_storing_new_posts_does_not_touch_legacy_rows(app_client):
    """Das Speichern neuer Beiträge darf Bestandszeilen (data_version NULL)
    nicht anfassen - kein Backfill, keine nachträgliche Anreicherung."""
    from app.db import SessionLocal
    from app.models import Post
    from app.scheduler import engine

    now = datetime.now(timezone.utc)
    async with SessionLocal() as s:
        legacy = Post(
            platform="news", source="legacy", external_id="v2-untouched-1",
            content_hash="v2-untouched-hash-1", text="Unveränderter Bestandstext",
            created_at=now, collected_at=now,
        )
        s.add(legacy)
        await s.commit()
        await s.refresh(legacy)
        post_id = legacy.id

    # Ein unabhängiger neuer Sammel-Lauf, der mit dem Bestandspost nichts zu tun hat
    fresh = RawItem(platform="bluesky", external_id="v2-untouched-2", text="Neuer Beitrag über Docker", created_at=now)
    await engine._store([fresh], ["docker"])

    async with SessionLocal() as s:
        still_legacy = await s.get(Post, post_id)
    assert still_legacy.text == "Unveränderter Bestandstext"
    assert still_legacy.data_version in (None, 1)
    assert still_legacy.content_status is None
    assert still_legacy.raw_payload is None

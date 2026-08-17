"""Collector-Tests gegen gemockte HTTP-Antworten (kein echtes Netz nötig)."""
import httpx
import pytest

from app.collectors import (
    BlueskyCollector,
    FacebookCollector,
    NewsCollector,
    RedditCollector,
    XCollector,
)
from app.config import settings

BSKY_RESPONSE = {
    "posts": [
        {
            "uri": "at://did:plc:abc/app.bsky.feed.post/3k1",
            "cid": "bafy1",
            "author": {"handle": "someone.bsky.social", "displayName": "Some One"},
            "record": {
                "text": "Neue Ransomware-Welle trifft Kliniken. CVE-2026-1111",
                "createdAt": "2026-08-13T10:00:00.000Z",
                "langs": ["de"],
            },
            "likeCount": 12,
            "repostCount": 3,
            "replyCount": 1,
        }
    ]
}

REDDIT_RESPONSE = {
    "data": {
        "children": [
            {
                "data": {
                    "name": "t3_abc123",
                    "id": "abc123",
                    "title": "Linux 7.0 released",
                    "selftext": "Der neue Kernel bringt Docker-Verbesserungen.",
                    "author": "kernelfan",
                    "subreddit": "linux",
                    "permalink": "/r/linux/comments/abc123/linux_70/",
                    "created_utc": 1786000000,
                    "score": 420,
                    "num_comments": 42,
                }
            }
        ]
    }
}

RSS_FEED = """<?xml version="1.0"?>
<rss version="2.0"><channel>
<item>
  <title>BSI warnt vor kritischer Lücke</title>
  <description>&lt;p&gt;CVE-2026-2222 wird aktiv ausgenutzt.&lt;/p&gt;</description>
  <link>https://example.org/advisory/1</link>
  <pubDate>Wed, 13 Aug 2026 08:00:00 GMT</pubDate>
  <guid>adv-1</guid>
</item>
</channel></rss>"""


def make_client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_bluesky_parses_posts():
    def handler(request: httpx.Request) -> httpx.Response:
        assert "searchPosts" in str(request.url)
        return httpx.Response(200, json=BSKY_RESPONSE)

    async with make_client(handler) as client:
        items = await BlueskyCollector(client).fetch(["ransomware"])

    assert len(items) == 1
    it = items[0]
    assert it.platform == "bluesky"
    assert it.author_handle == "someone.bsky.social"
    assert it.url == "https://bsky.app/profile/someone.bsky.social/post/3k1"
    assert it.engagement["likes"] == 12
    assert it.created_at.year == 2026


@pytest.mark.asyncio
async def test_bluesky_empty_terms_returns_nothing():
    async with make_client(lambda r: httpx.Response(200, json={})) as client:
        assert await BlueskyCollector(client).fetch([]) == []


@pytest.mark.asyncio
async def test_reddit_parses_listing():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=REDDIT_RESPONSE)

    async with make_client(handler) as client:
        items = await RedditCollector(client).fetch(["linux"])

    assert items
    it = items[0]
    assert it.platform == "reddit"
    assert it.source == "r/linux"
    assert it.url.startswith("https://www.reddit.com/r/linux/comments/")
    assert it.engagement["score"] == 420


@pytest.mark.asyncio
async def test_reddit_falls_back_to_rss_on_403():
    calls = {"json": 0, "rss": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).endswith(".rss") or "search.rss" in str(request.url):
            calls["rss"] += 1
            return httpx.Response(200, text=RSS_FEED)
        calls["json"] += 1
        return httpx.Response(403, text="blocked")

    async with make_client(handler) as client:
        items = await RedditCollector(client).fetch(["linux"])

    assert calls["rss"] >= 1
    assert any(i.raw.get("mode") == "rss" for i in items)


@pytest.mark.asyncio
async def test_news_parses_feed_and_sets_category_hint():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=RSS_FEED.encode())

    async with make_client(handler) as client:
        items = await NewsCollector(client).fetch(["cve"])

    assert items
    it = items[0]
    assert it.platform == "news"
    assert it.category_hint in {"cybersecurity", "it", "nachrichten", "alltag"}
    # HTML wurde entfernt
    assert "<p>" not in it.text
    assert "CVE-2026-2222" in it.text


@pytest.mark.asyncio
async def test_x_inactive_without_config():
    async with make_client(lambda r: httpx.Response(200, json={})) as client:
        col = XCollector(client)
        ok, reason = col.available()
        assert ok is False
        assert "nicht konfiguriert" in reason
        assert await col.fetch(["test"]) == []


@pytest.mark.asyncio
async def test_x_uses_api_when_token_present(monkeypatch):
    monkeypatch.setattr(settings, "x_bearer_token", "TESTTOKEN")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer TESTTOKEN"
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "111",
                        "text": "Sicherheitslücke gefunden",
                        "created_at": "2026-08-13T09:00:00.000Z",
                        "author_id": "u1",
                        "lang": "de",
                        "public_metrics": {"like_count": 5, "retweet_count": 2,
                                           "reply_count": 0, "quote_count": 0},
                    }
                ],
                "includes": {"users": [{"id": "u1", "username": "tester", "name": "Tester"}]},
            },
        )

    async with make_client(handler) as client:
        col = XCollector(client)
        assert col.available()[0] is True
        items = await col.fetch(["sicherheitslücke"])

    assert items[0].url == "https://x.com/tester/status/111"
    assert items[0].author_handle == "@tester"
    monkeypatch.setattr(settings, "x_bearer_token", "")


@pytest.mark.asyncio
async def test_facebook_inactive_without_config():
    async with make_client(lambda r: httpx.Response(200, json={})) as client:
        col = FacebookCollector(client)
        assert col.available()[0] is False
        assert await col.fetch(["test"]) == []


@pytest.mark.asyncio
async def test_facebook_graph_mode(monkeypatch):
    monkeypatch.setattr(settings, "facebook_page_token", "TOK")
    monkeypatch.setattr(settings, "facebook_page_ids", "12345")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "12345_9",
                        "message": "Hallo von der Seite",
                        "created_time": "2026-08-13T07:00:00+0000",
                        "permalink_url": "https://facebook.com/12345_9",
                        "from": {"name": "Meine Seite", "id": "12345"},
                    }
                ]
            },
        )

    async with make_client(handler) as client:
        col = FacebookCollector(client)
        assert col.available()[0] is True
        items = await col.fetch([])

    assert items[0].text == "Hallo von der Seite"
    assert items[0].platform == "facebook"
    monkeypatch.setattr(settings, "facebook_page_token", "")
    monkeypatch.setattr(settings, "facebook_page_ids", "")

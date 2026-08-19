"""Collector-Tests gegen gemockte HTTP-Antworten (kein echtes Netz nötig)."""
import httpx
import pytest

from app.collectors import (
    BlueskyCollector,
    FacebookCollector,
    GoogleNewsCollector,
    NewsCollector,
    RedditCollector,
    XCollector,
)
from app.collectors.base import BaseCollector, CollectorError
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

GOOGLENEWS_FEED = """<?xml version="1.0"?>
<rss version="2.0"><channel>
<item>
  <title>BSI warnt vor kritischer Lücke - heise online</title>
  <link>https://news.google.com/rss/articles/abc123</link>
  <description>&lt;a href="..."&gt;BSI warnt vor kritischer Lücke&lt;/a&gt;&amp;nbsp;&amp;nbsp;&lt;font color="#6f6f6f"&gt;heise online&lt;/font&gt;</description>
  <pubDate>Wed, 13 Aug 2026 08:00:00 GMT</pubDate>
  <guid>gn-1</guid>
  <source url="https://www.heise.de">heise online</source>
</item>
</channel></rss>"""


def make_client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


class _DummyCollector(BaseCollector):
    """Minimaler konkreter Collector nur für die Backoff-Tests."""

    name = "dummy"
    platform = "dummy"
    label = "Dummy"

    async def fetch(self, terms):  # pragma: no cover - hier ungenutzt
        return []


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
async def test_googlenews_parses_feed_and_strips_source_suffix():
    def handler(request: httpx.Request) -> httpx.Response:
        assert "news.google.com/rss/search" in str(request.url)
        assert request.url.params.get("q") == "cve"
        return httpx.Response(200, content=GOOGLENEWS_FEED.encode())

    async with make_client(handler) as client:
        items = await GoogleNewsCollector(client).fetch(["cve"])

    assert items
    it = items[0]
    assert it.platform == "googlenews"
    assert it.source == "heise online"
    assert it.author == "heise online"
    # " - heise online" wird vom Titel gestrippt, weil die Quelle separat gezeigt wird
    assert it.title == "BSI warnt vor kritischer Lücke"
    assert "<a href" not in it.text


@pytest.mark.asyncio
async def test_googlenews_empty_terms_returns_nothing():
    async with make_client(lambda r: httpx.Response(200, content=b"")) as client:
        assert await GoogleNewsCollector(client).fetch([]) == []


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


@pytest.mark.asyncio
async def test_backoff_retries_on_429_then_succeeds(monkeypatch):
    slept: list[float] = []

    async def fake_sleep(seconds):
        slept.append(seconds)

    monkeypatch.setattr("app.collectors.base.asyncio.sleep", fake_sleep)

    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 2:
            return httpx.Response(429, headers={"Retry-After": "3"}, text="slow down")
        return httpx.Response(200, json={"ok": True})

    async with make_client(handler) as client:
        resp = await _DummyCollector(client)._get_with_backoff("https://example.org/x")

    assert resp.status_code == 200
    assert calls["n"] == 2
    # Retry-After-Header wurde respektiert (3s, plus 0-25% Jitter)
    assert slept and 3.0 <= slept[0] <= 3.75


@pytest.mark.asyncio
async def test_backoff_uses_exponential_delay_without_retry_after(monkeypatch):
    slept: list[float] = []

    async def fake_sleep(seconds):
        slept.append(seconds)

    monkeypatch.setattr("app.collectors.base.asyncio.sleep", fake_sleep)

    async with make_client(lambda r: httpx.Response(429, text="limited")) as client:
        with pytest.raises(CollectorError, match="Wiederholungen erschöpft"):
            await _DummyCollector(client)._get_with_backoff(
                "https://example.org/x", max_retries=2, base_delay=1.0
            )

    # 2 Wiederholungen -> Delays ~1.0s und ~2.0s (jeweils + bis zu 25% Jitter)
    assert len(slept) == 2
    assert 1.0 <= slept[0] <= 1.25
    assert 2.0 <= slept[1] <= 2.5


@pytest.mark.asyncio
async def test_backoff_does_not_retry_non_429_errors(monkeypatch):
    calls = {"n": 0}

    async def fake_sleep(seconds):  # sollte nicht aufgerufen werden
        raise AssertionError("sleep sollte bei Nicht-429-Fehlern nicht passieren")

    monkeypatch.setattr("app.collectors.base.asyncio.sleep", fake_sleep)

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(500, text="server error")

    async with make_client(handler) as client:
        with pytest.raises(CollectorError, match="HTTP 500"):
            await _DummyCollector(client)._get_with_backoff("https://example.org/x")

    assert calls["n"] == 1

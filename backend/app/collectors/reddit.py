"""Reddit.

Drei Modi, in dieser Reihenfolge:
  1. OAuth (REDDIT_CLIENT_ID/SECRET, App-Typ "script")  -> beste Limits
  2. öffentliche JSON-API (www.reddit.com/....json)     -> ohne Login
  3. RSS-Rückfall (.rss)                                -> wenn JSON blockt

Gesammelt wird beides: Suchtreffer zu den Begriffen + die neuesten
Beiträge aus den konfigurierten Subreddits.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

import feedparser

from ..config import settings
from .base import BaseCollector, CollectorError, RawItem, strip_html

log = logging.getLogger("netzwache.collector.reddit")

PUBLIC = "https://www.reddit.com"
OAUTH = "https://oauth.reddit.com"


class RedditCollector(BaseCollector):
    name = "reddit"
    platform = "reddit"
    label = "Reddit"
    default_interval = settings.interval_reddit
    setup_hint = (
        "Läuft ohne Login über die öffentliche JSON-API. Für stabile Limits "
        "unter reddit.com/prefs/apps eine App vom Typ 'script' anlegen und "
        "REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET setzen."
    )

    def __init__(self, client) -> None:
        super().__init__(client)
        self._token: str | None = None
        self._token_at: datetime | None = None
        self._mode = "public"

    def available(self) -> tuple[bool, str]:
        if settings.reddit_client_id and settings.reddit_client_secret:
            return True, "OAuth (script-App)"
        return True, "öffentliche JSON-API"

    # ------------------------------------------------------------------
    async def _ensure_token(self) -> str | None:
        if not (settings.reddit_client_id and settings.reddit_client_secret):
            return None
        fresh = (
            self._token
            and self._token_at
            and (datetime.now(timezone.utc) - self._token_at).total_seconds() < 45 * 60
        )
        if fresh:
            return self._token
        resp = await self.client.post(
            "https://www.reddit.com/api/v1/access_token",
            data={"grant_type": "client_credentials"},
            auth=(settings.reddit_client_id, settings.reddit_client_secret),
            headers={"User-Agent": settings.user_agent},
            timeout=settings.http_timeout,
        )
        if resp.status_code >= 400:
            raise CollectorError(f"OAuth fehlgeschlagen: HTTP {resp.status_code}")
        self._token = resp.json().get("access_token")
        self._token_at = datetime.now(timezone.utc)
        return self._token

    async def _listing(self, path: str, params: dict) -> list[dict]:
        """Ruft ein Reddit-Listing ab (OAuth bevorzugt, sonst öffentlich)."""
        token = await self._ensure_token()
        if token:
            self._mode = "oauth"
            resp = await self._get(
                f"{OAUTH}{path}",
                params=params,
                headers={"Authorization": f"Bearer {token}"},
            )
        else:
            self._mode = "public"
            resp = await self._get(f"{PUBLIC}{path}.json", params={**params, "raw_json": 1})
        data = resp.json()
        return [c.get("data", {}) for c in data.get("data", {}).get("children", [])]

    async def _rss_fallback(self, term: str) -> list[RawItem]:
        resp = await self._get(f"{PUBLIC}/search.rss", params={"q": term, "sort": "new"})
        feed = feedparser.parse(resp.text)
        out: list[RawItem] = []
        for e in feed.entries[:20]:
            link = e.get("link", "")
            title = strip_html(e.get("title", ""), 500)
            body = strip_html(e.get("summary", "") or e.get("description", ""))
            # Reddit wiederholt im RSS-Body oft nur den Titel -> dann leer lassen
            if body and body.strip().lower() == title.strip().lower():
                body = ""
            author = (e.get("author") or "").strip()
            sub = self._subreddit_from_link(link)
            out.append(
                RawItem(
                    platform="reddit",
                    external_id=e.get("id") or link,
                    title=title,
                    text=body or title,
                    url=link,
                    author=author.lstrip("/").removeprefix("u/"),
                    author_handle=author if author.startswith("/u/") else (f"u/{author.lstrip('/u/')}" if author else ""),
                    source=f"r/{sub}" if sub else "reddit/rss",
                    created_at=self._parse_struct(e),
                    raw={"mode": "rss", "term": term, "subreddit": sub},
                )
            )
        return out

    @staticmethod
    def _subreddit_from_link(link: str) -> str:
        m = re.search(r"/r/([\w\-]+)/", link or "")
        return m.group(1) if m else ""

    @staticmethod
    def _parse_struct(entry) -> datetime:
        st = entry.get("published_parsed") or entry.get("updated_parsed")
        if st:
            return datetime(*st[:6], tzinfo=timezone.utc)
        return datetime.now(timezone.utc)

    # ------------------------------------------------------------------
    async def fetch(self, terms: list[str]) -> list[RawItem]:
        items: list[RawItem] = []
        errors: list[str] = []

        # 1) Suchbegriffe
        for term in terms[:8]:
            try:
                rows = await self._listing("/search", {"q": term, "sort": "new", "limit": 15, "t": "day"})
                items.extend(self._to_item(r, term) for r in rows)
            except CollectorError as exc:
                log.debug("Reddit-Suche '%s' fehlgeschlagen: %s", term, exc)
                try:
                    items.extend(await self._rss_fallback(term))
                except CollectorError as exc2:
                    errors.append(f"{term}: {exc2}")

        # 2) Feste Subreddits (liefert auch ohne Treffer laufend Material)
        for sub in settings.subreddit_list[:10]:
            try:
                rows = await self._listing(f"/r/{sub}/new", {"limit": 10})
                items.extend(self._to_item(r, "") for r in rows)
            except CollectorError as exc:
                errors.append(f"r/{sub}: {exc}")

        if not items and errors:
            raise CollectorError("; ".join(errors[:3]))
        return items

    def _to_item(self, r: dict, term: str) -> RawItem:
        created = r.get("created_utc")
        created_at = (
            datetime.fromtimestamp(float(created), tz=timezone.utc)
            if created
            else datetime.now(timezone.utc)
        )
        sub = r.get("subreddit", "")
        title = strip_html(r.get("title", ""), 500)
        body = strip_html(r.get("selftext") or "")
        return RawItem(
            platform="reddit",
            external_id=r.get("name") or f"t3_{r.get('id','')}",
            title=title,
            text=body or title,
            url="https://www.reddit.com" + r.get("permalink", "") if r.get("permalink") else r.get("url", ""),
            author=r.get("author", ""),
            author_handle=f"u/{r.get('author','')}" if r.get("author") else "",
            source=f"r/{sub}" if sub else "reddit",
            created_at=created_at,
            engagement={
                "score": r.get("score", 0),
                "comments": r.get("num_comments", 0),
                "ratio": r.get("upvote_ratio", 0),
            },
            raw={"mode": self._mode, "term": term, "subreddit": sub, "flair": r.get("link_flair_text")},
        )

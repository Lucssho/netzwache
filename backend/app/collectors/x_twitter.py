"""X (Twitter).

Stand 2026 gibt es keine brauchbare kostenlose Lese-API mehr. Der Adapter
ist deshalb als Slot gebaut und aktiviert sich automatisch, sobald einer
dieser Wege konfiguriert ist:

  1. X_BEARER_TOKEN  -> offizielle API v2 (/2/tweets/search/recent)
  2. NITTER_INSTANCES -> RSS eines Nitter-Mirrors (unzuverlässig, kein Login)

Ohne beides meldet der Collector sauber "nicht konfiguriert" ans Frontend,
statt die Sammelschleife mit Fehlern zu fluten.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import feedparser
from dateutil import parser as dtparse

from ..config import settings
from .base import BaseCollector, CollectorError, RawItem, strip_html

log = logging.getLogger("netzwache.collector.x")


class XCollector(BaseCollector):
    name = "x"
    platform = "x"
    label = "X / Twitter"
    default_interval = settings.interval_x
    setup_hint = (
        "X bietet keine kostenlose Lese-API mehr. Entweder X_BEARER_TOKEN "
        "(kostenpflichtiger Basic-/Pro-Plan, developer.x.com) oder "
        "NITTER_INSTANCES=https://nitter.example,https://xcancel.com in der "
        ".env setzen. Ohne beides bleibt die Quelle inaktiv."
    )

    def available(self) -> tuple[bool, str]:
        if settings.x_bearer_token:
            return True, "offizielle API v2 (Bearer-Token)"
        if settings.nitter_list:
            return True, f"Nitter-Mirror ({len(settings.nitter_list)} Instanz(en))"
        return False, "nicht konfiguriert - X_BEARER_TOKEN oder NITTER_INSTANCES setzen"

    # ------------------------------------------------------------------
    async def fetch(self, terms: list[str]) -> list[RawItem]:
        ok, _ = self.available()
        if not ok or not terms:
            return []
        if settings.x_bearer_token:
            return await self._fetch_api(terms)
        return await self._fetch_nitter(terms)

    # --- offizielle API -------------------------------------------------
    async def _fetch_api(self, terms: list[str]) -> list[RawItem]:
        query = " OR ".join(f'"{t}"' for t in terms[:8]) + " -is:retweet"
        resp = await self._get(
            f"{settings.x_api_base}/tweets/search/recent",
            params={
                "query": query[:500],
                "max_results": min(100, max(10, settings.max_items_per_run)),
                "tweet.fields": "created_at,public_metrics,lang,author_id",
                "expansions": "author_id",
                "user.fields": "username,name",
            },
            headers={"Authorization": f"Bearer {settings.x_bearer_token}"},
        )
        data = resp.json()
        users = {u["id"]: u for u in data.get("includes", {}).get("users", [])}
        items: list[RawItem] = []
        for t in data.get("data", []):
            u = users.get(t.get("author_id"), {})
            handle = u.get("username", "")
            try:
                created = dtparse.isoparse(t["created_at"])
            except Exception:
                created = self._now()
            m = t.get("public_metrics", {})
            items.append(
                RawItem(
                    platform="x",
                    external_id=f"x:{t['id']}",
                    text=t.get("text", ""),
                    url=f"https://x.com/{handle}/status/{t['id']}" if handle else f"https://x.com/i/status/{t['id']}",
                    author=u.get("name", handle),
                    author_handle=f"@{handle}" if handle else "",
                    lang=t.get("lang", ""),
                    source="x/api-v2",
                    created_at=created,
                    engagement={
                        "likes": m.get("like_count", 0),
                        "reposts": m.get("retweet_count", 0),
                        "replies": m.get("reply_count", 0),
                        "quotes": m.get("quote_count", 0),
                    },
                    raw={"mode": "api"},
                )
            )
        return items

    # --- Nitter-RSS -----------------------------------------------------
    async def _fetch_nitter(self, terms: list[str]) -> list[RawItem]:
        items: list[RawItem] = []
        errors: list[str] = []
        for term in terms[:5]:
            got = False
            for base in settings.nitter_list:
                try:
                    resp = await self._get(
                        f"{base}/search/rss", params={"f": "tweets", "q": term}
                    )
                    feed = feedparser.parse(resp.text)
                    for e in feed.entries[:15]:
                        items.append(self._nitter_item(e, term))
                    got = True
                    break
                except CollectorError as exc:
                    errors.append(f"{base}: {exc}")
            if not got:
                log.debug("Kein Nitter-Mirror erreichbar für '%s'", term)
        if not items and errors:
            raise CollectorError("Nitter nicht erreichbar: " + "; ".join(errors[:2]))
        return items

    def _nitter_item(self, e, term: str) -> RawItem:
        link = (e.get("link") or "").replace("nitter.net", "x.com")
        for base in settings.nitter_list:
            link = link.replace(base, "https://x.com")
        st = e.get("published_parsed")
        created = datetime(*st[:6], tzinfo=timezone.utc) if st else self._now()
        creator = e.get("author") or e.get("dc_creator") or ""
        return RawItem(
            platform="x",
            external_id=f"x:{e.get('id') or e.get('link','')}",
            text=strip_html(e.get("description") or e.get("title", "")),
            url=link,
            author=creator,
            author_handle=creator if creator.startswith("@") else (f"@{creator}" if creator else ""),
            source="x/nitter",
            created_at=created,
            raw={"mode": "nitter", "term": term},
        )

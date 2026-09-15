"""Facebook.

Öffentliches Scrapen von Facebook ist technisch blockiert und verstößt
gegen die Nutzungsbedingungen. Legal nutzbar sind:

  1. Graph API mit Page-Access-Token für Seiten, die du selbst verwaltest
     (FACEBOOK_PAGE_TOKEN + FACEBOOK_PAGE_IDS)
  2. eine selbstgehostete RSS-Bridge (RSSBRIDGE_URL) für öffentliche Seiten

Ohne Konfiguration meldet der Adapter sauber "inaktiv".
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import feedparser
from dateutil import parser as dtparse

from ..config import settings
from .base import BaseCollector, CollectorError, RawItem, strip_html

log = logging.getLogger("netzwache.collector.facebook")


class FacebookCollector(BaseCollector):
    name = "facebook"
    platform = "facebook"
    label = "Facebook"
    default_interval = settings.interval_facebook
    setup_hint = (
        "Facebook erlaubt kein öffentliches Scrapen. Entweder Graph API "
        "(FACEBOOK_PAGE_TOKEN + FACEBOOK_PAGE_IDS für eigene Seiten) oder "
        "eine selbstgehostete RSS-Bridge (RSSBRIDGE_URL) konfigurieren."
    )

    def available(self) -> tuple[bool, str]:
        if settings.facebook_page_token and settings.facebook_page_list:
            return True, f"Graph API ({len(settings.facebook_page_list)} Seite(n))"
        if settings.rssbridge_url:
            return True, "RSS-Bridge"
        return False, "nicht konfiguriert - Graph-Token oder RSS-Bridge nötig"

    async def fetch(self, terms: list[str]) -> list[RawItem]:
        ok, _ = self.available()
        if not ok:
            return []
        if settings.facebook_page_token and settings.facebook_page_list:
            return await self._fetch_graph()
        return await self._fetch_bridge(terms)

    # ------------------------------------------------------------------
    async def _fetch_graph(self) -> list[RawItem]:
        items: list[RawItem] = []
        errors: list[str] = []
        for page_id in settings.facebook_page_list:
            try:
                resp = await self._get(
                    f"{settings.facebook_graph_base}/{page_id}/posts",
                    params={
                        "fields": "id,message,created_time,permalink_url,from{name,id},shares",
                        "limit": 25,
                        "access_token": settings.facebook_page_token,
                    },
                )
            except CollectorError as exc:
                errors.append(f"{page_id}: {exc}")
                continue
            for p in resp.json().get("data", []):
                if not p.get("message"):
                    continue
                try:
                    created = dtparse.isoparse(p["created_time"])
                except Exception:
                    created = self._now()
                who = (p.get("from") or {}).get("name", page_id)
                # Facebooks Graph API lässt das "shares"-Objekt bei 0 Shares
                # oft ganz weg, statt {"count": 0} zu liefern - .get(...) ohne
                # Default unterscheidet das ehrlich von einem echten Nullwert
                # (siehe README, Engagement als Momentaufnahme).
                shares = p.get("shares")
                message = p.get("message", "")
                items.append(
                    RawItem(
                        platform="facebook",
                        external_id=f"fb:{p['id']}",
                        text=message,
                        url=p.get("permalink_url", ""),
                        author=who,
                        author_handle=str(page_id),
                        source=f"fb/{who}",
                        created_at=created,
                        engagement={"shares": shares.get("count")} if shares else {},
                        raw={"mode": "graph"},
                        content_type="post",
                        content_status="full",
                        content_full=message,
                        collector_mode="graph",
                        raw_payload=p,
                    )
                )
        if not items and errors:
            raise CollectorError("; ".join(errors[:3]))
        return items

    async def _fetch_bridge(self, terms: list[str]) -> list[RawItem]:
        resp = await self._get(settings.rssbridge_url)
        return await asyncio.to_thread(self._parse_bridge, resp.text)

    def _parse_bridge(self, content: str) -> list[RawItem]:
        """XML-Parsing + HTML-Bereinigung - CPU-lastig, läuft per to_thread."""
        feed = feedparser.parse(content)
        items: list[RawItem] = []
        for e in feed.entries[:25]:
            st = e.get("published_parsed")
            created = datetime(*st[:6], tzinfo=timezone.utc) if st else self._now()
            title = strip_html(e.get("title", ""), 500)
            body = strip_html(e.get("summary", ""))
            items.append(
                RawItem(
                    platform="facebook",
                    external_id=f"fb:{e.get('id') or e.get('link','')}",
                    title=title,
                    text=body,
                    url=e.get("link", ""),
                    author=e.get("author", "Facebook"),
                    source="fb/rss-bridge",
                    created_at=created,
                    raw={"mode": "rssbridge"},
                    # Eine RSS-Bridge liefert bestenfalls eine Zusammenfassung
                    # des Original-Posts, nie zuverlässig den vollen Text.
                    content_type="post",
                    content_status="summary" if body else "title_only",
                    summary=body or "",
                    collector_mode="rss_bridge",
                    raw_payload={
                        "id": e.get("id"),
                        "link": e.get("link"),
                        "title": e.get("title"),
                        "summary": e.get("summary"),
                        "author": e.get("author"),
                    },
                )
            )
        return items

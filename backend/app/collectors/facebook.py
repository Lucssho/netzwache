"""Facebook.

Öffentliches Scrapen von Facebook ist technisch blockiert und verstößt
gegen die Nutzungsbedingungen. Legal nutzbar sind:

  1. Graph API mit Page-Access-Token für Seiten, die du selbst verwaltest
     (FACEBOOK_PAGE_TOKEN + FACEBOOK_PAGE_IDS)
  2. eine selbstgehostete RSS-Bridge (RSSBRIDGE_URL) für öffentliche Seiten

Ohne Konfiguration meldet der Adapter sauber "inaktiv".
"""
from __future__ import annotations

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
                items.append(
                    RawItem(
                        platform="facebook",
                        external_id=f"fb:{p['id']}",
                        text=p.get("message", ""),
                        url=p.get("permalink_url", ""),
                        author=who,
                        author_handle=str(page_id),
                        source=f"fb/{who}",
                        created_at=created,
                        engagement={"shares": (p.get("shares") or {}).get("count", 0)},
                        raw={"mode": "graph"},
                    )
                )
        if not items and errors:
            raise CollectorError("; ".join(errors[:3]))
        return items

    async def _fetch_bridge(self, terms: list[str]) -> list[RawItem]:
        resp = await self._get(settings.rssbridge_url)
        feed = feedparser.parse(resp.text)
        items: list[RawItem] = []
        for e in feed.entries[:25]:
            st = e.get("published_parsed")
            created = datetime(*st[:6], tzinfo=timezone.utc) if st else self._now()
            items.append(
                RawItem(
                    platform="facebook",
                    external_id=f"fb:{e.get('id') or e.get('link','')}",
                    title=strip_html(e.get("title", ""), 500),
                    text=strip_html(e.get("summary", "")),
                    url=e.get("link", ""),
                    author=e.get("author", "Facebook"),
                    source="fb/rss-bridge",
                    created_at=created,
                    raw={"mode": "rssbridge"},
                )
            )
        return items

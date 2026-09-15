"""Google News (RSS-Suche).

Durchsucht Google News pro aktivem Suchbegriff über den öffentlichen
RSS-Endpunkt - kein API-Key, kein Login nötig. Google News ist ein reiner
Aggregator: jeder Eintrag verlinkt über eine Google-Weiterleitung auf den
Original-Artikel der jeweiligen Quelle, die im Feed als <source> mitgeliefert
wird.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import feedparser

from ..config import settings
from .base import BaseCollector, CollectorError, RawItem, strip_html

log = logging.getLogger("netzwache.collector.googlenews")

SEARCH_URL = "https://news.google.com/rss/search"


class GoogleNewsCollector(BaseCollector):
    name = "googlenews"
    platform = "googlenews"
    label = "Google News"
    default_interval = settings.interval_googlenews
    setup_hint = "Keine Konfiguration nötig - durchsucht Google News RSS pro Suchbegriff."

    def available(self) -> tuple[bool, str]:
        return True, "öffentliche RSS-Suche"

    async def fetch(self, terms: list[str]) -> list[RawItem]:
        if not terms:
            return []
        items: list[RawItem] = []
        errors: list[str] = []

        for term in terms[:8]:
            try:
                resp = await self._get(
                    SEARCH_URL,
                    params={"q": term, "hl": "de", "gl": "DE", "ceid": "DE:de"},
                )
            except CollectorError as exc:
                errors.append(f"{term}: {exc}")
                continue
            items.extend(await asyncio.to_thread(self._parse_feed, resp.content, term))

        if not items and errors:
            raise CollectorError("; ".join(errors[:3]))
        return items

    def _parse_feed(self, content: bytes, term: str) -> list[RawItem]:
        """XML-Parsing + HTML-Bereinigung - CPU-lastig, läuft per to_thread."""
        feed = feedparser.parse(content)
        return [self._to_item(e, term) for e in feed.entries[:15]]

    def _to_item(self, e: dict, term: str) -> RawItem:
        source = (e.get("source") or {}).get("title", "")
        title = strip_html(e.get("title") or "", 500)
        # Google News hängt an jeden Titel " - Quellenname" an - für die
        # Anzeige redundant, weil die Quelle schon separat gezeigt wird.
        if source and title.endswith(f" - {source}"):
            title = title[: -(len(source) + 3)].strip()
        summary = strip_html(e.get("summary") or e.get("description") or "")
        if summary.strip().lower() == title.strip().lower():
            summary = ""
        st = e.get("published_parsed") or e.get("updated_parsed")
        created = datetime(*st[:6], tzinfo=timezone.utc) if st else self._now()
        # Datenformat v2: `link` ist eine Google-Weiterleitung, keine
        # Publisher-URL - sie ohne weiteren Request aufzulösen geht bei
        # Google News nicht zuverlässig (die Umleitung läuft per JavaScript,
        # nicht per HTTP-Redirect), deshalb bleibt canonical_url hier bewusst
        # leer statt eine falsche URL zu behaupten (siehe README).
        return RawItem(
            platform="googlenews",
            external_id=f"googlenews:{e.get('id') or e.get('link', '')}",
            title=title,
            text=summary or title,
            url=e.get("link", ""),
            author=source or "Google News",
            source=source or "Google News",
            created_at=created,
            raw={"term": term, "source": source},
            content_type="article",
            content_status="summary" if summary else "title_only",
            summary=summary or "",
            raw_payload={
                "term": term,
                "source_title": source,
                "source_url": (e.get("source") or {}).get("href"),
                "link": e.get("link"),
                "title": e.get("title"),
                "summary": e.get("summary") or e.get("description"),
                "published": e.get("published") or e.get("updated"),
            },
        )

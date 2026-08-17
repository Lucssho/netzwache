"""Kuratierte News-/Security-Feeds (RSS/Atom).

Diese Quelle braucht keinerlei Keys und liefert deshalb dauerhaft Daten -
auch dann, wenn X und Facebook nicht konfiguriert sind. Die Feeds sind
nach den vier Zielkategorien sortiert.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import feedparser

from ..config import settings
from .base import BaseCollector, CollectorError, RawItem, strip_html

log = logging.getLogger("netzwache.collector.news")

# (Anzeigename, URL, Kategorie)
FEEDS: list[tuple[str, str, str]] = [
    # --- Cybersecurity -------------------------------------------------
    ("BSI CERT-Bund", "https://wid.cert-bund.de/content/public/securityAdvisory/rss", "cybersecurity"),
    ("heise Security", "https://www.heise.de/security/rss/news-atom.xml", "cybersecurity"),
    ("BleepingComputer", "https://www.bleepingcomputer.com/feed/", "cybersecurity"),
    ("The Hacker News", "https://feeds.feedburner.com/TheHackersNews", "cybersecurity"),
    ("Krebs on Security", "https://krebsonsecurity.com/feed/", "cybersecurity"),
    ("CISA Advisories", "https://www.cisa.gov/cybersecurity-advisories/all.xml", "cybersecurity"),
    ("Golem Security", "https://rss.golem.de/rss.php?tp=sec&feed=RSS2.0", "cybersecurity"),
    # --- IT -------------------------------------------------------------
    ("heise online", "https://www.heise.de/rss/heise-atom.xml", "it"),
    ("Golem.de", "https://rss.golem.de/rss.php?feed=RSS2.0", "it"),
    ("Hacker News", "https://hnrss.org/frontpage", "it"),
    ("LWN.net", "https://lwn.net/headlines/rss", "it"),
    ("Phoronix", "https://www.phoronix.com/rss.php", "it"),
    ("Linux Weekly (t3n)", "https://t3n.de/rss.xml", "it"),
    # --- Nachrichten -----------------------------------------------------
    ("tagesschau", "https://www.tagesschau.de/index~rss2.xml", "nachrichten"),
    ("ZEIT ONLINE", "https://newsfeed.zeit.de/index", "nachrichten"),
    ("Deutsche Welle", "https://rss.dw.com/rdf/rss-de-all", "nachrichten"),
    ("Spiegel", "https://www.spiegel.de/schlagzeilen/tops/index.rss", "nachrichten"),
    # --- Alltag -----------------------------------------------------------
    ("tagesschau Inland", "https://www.tagesschau.de/inland/index~rss2.xml", "alltag"),
    ("ZEIT Gesellschaft", "https://newsfeed.zeit.de/gesellschaft/index", "alltag"),
    ("Utopia (Alltag)", "https://utopia.de/feed/", "alltag"),
]


class NewsCollector(BaseCollector):
    name = "news"
    platform = "news"
    label = "News & Security-Feeds"
    default_interval = settings.interval_news
    setup_hint = "Keine Konfiguration nötig - läuft sofort."

    def __init__(self, client) -> None:
        super().__init__(client)
        self._cursor = 0  # rotiert die Feeds, damit ein Lauf kurz bleibt

    def available(self) -> tuple[bool, str]:
        return True, f"{len(FEEDS)} Feeds"

    async def fetch(self, terms: list[str]) -> list[RawItem]:
        batch = 6
        selected = [FEEDS[(self._cursor + i) % len(FEEDS)] for i in range(batch)]
        self._cursor = (self._cursor + batch) % len(FEEDS)

        items: list[RawItem] = []
        errors: list[str] = []
        low_terms = [t.lower() for t in terms]

        for label, url, category in selected:
            try:
                resp = await self._get(url)
            except CollectorError as exc:
                errors.append(f"{label}: {exc}")
                continue
            feed = feedparser.parse(resp.content)
            for e in feed.entries[:15]:
                title = strip_html(e.get("title") or "", 500)
                summary = strip_html(e.get("summary") or e.get("description") or "")
                if summary.strip().lower() == title.strip().lower():
                    summary = ""
                blob = f"{title} {summary}".lower()
                if low_terms and not settings.news_keep_all:
                    if not any(t in blob for t in low_terms):
                        continue
                st = e.get("published_parsed") or e.get("updated_parsed")
                created = datetime(*st[:6], tzinfo=timezone.utc) if st else self._now()
                items.append(
                    RawItem(
                        platform="news",
                        external_id=f"news:{e.get('id') or e.get('link','')}",
                        title=title,
                        text=summary or title,
                        url=e.get("link", ""),
                        author=label,
                        author_handle=label,
                        source=label,
                        category_hint=category,
                        created_at=created,
                        raw={"feed": url},
                    )
                )
        if not items and errors:
            raise CollectorError("; ".join(errors[:3]))
        return items

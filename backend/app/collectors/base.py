"""Basis für alle Collector-Adapter.

Jede Plattform implementiert genau diese Schnittstelle. Neue Quellen
hinzufügen = neue Datei + Eintrag in der Registry (collectors/__init__.py).
"""
from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup, Comment

from ..config import settings

log = logging.getLogger("netzwache.collector")

# Reddit hängt an jeden RSS-Eintrag einen Baustein
# "submitted by /u/name to r/sub [link] [comments]" - das ist kein Inhalt.
_REDDIT_BOILERPLATE = re.compile(
    r"\s*submitted\s+by\s*/?u/[\w\-]+\s*to\s*/?r/[\w\-]+\s*"
    r"(?:\[link\])?\s*(?:\[comments\])?\s*$",
    re.IGNORECASE,
)
_WS = re.compile(r"[ \t ]+")
_BLANKLINES = re.compile(r"\n{3,}")


def strip_html(raw: str, limit: int = 4000) -> str:
    """Macht aus HTML-Schnipseln (RSS-Feeds) sauberen Fließtext.

    Entfernt Tags, HTML-Kommentare wie <!-- SC_OFF -->, dekodiert Entities
    (&#32;, &amp; …) und schneidet den Reddit-Signaturblock ab.
    """
    if not raw:
        return ""
    text = raw
    if "<" in raw or "&" in raw:
        try:
            soup = BeautifulSoup(raw, "html.parser")
            for node in soup.find_all(string=lambda s: isinstance(s, Comment)):
                node.extract()
            for tag in soup.find_all(["script", "style"]):
                tag.decompose()
            for br in soup.find_all(["br", "p", "div", "li"]):
                br.append("\n")
            text = soup.get_text(" ")
        except Exception:  # pragma: no cover - defensiv
            text = re.sub(r"<[^>]+>", " ", raw)

    text = _WS.sub(" ", text)
    text = "\n".join(line.strip() for line in text.splitlines())
    text = _BLANKLINES.sub("\n\n", text).strip()
    text = _REDDIT_BOILERPLATE.sub("", text).strip()
    return text[:limit]


@dataclass
class RawItem:
    """Normalisierter Beitrag - plattformunabhängig."""

    platform: str
    external_id: str
    text: str = ""
    title: str = ""
    url: str = ""
    author: str = ""
    author_handle: str = ""
    lang: str = ""
    source: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    engagement: dict = field(default_factory=dict)
    category_hint: str = ""
    raw: dict = field(default_factory=dict)


class CollectorError(RuntimeError):
    """Fachlicher Fehler eines Collectors (wird im Status angezeigt)."""


class BaseCollector(ABC):
    name: str = "base"
    platform: str = "base"
    label: str = "Base"
    default_interval: int = 60
    #: Menschenlesbarer Hinweis, was für die Aktivierung fehlt
    setup_hint: str = ""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client

    # -- Verfügbarkeit -------------------------------------------------
    def available(self) -> tuple[bool, str]:
        """(nutzbar?, Begründung/Modus)."""
        return True, "bereit"

    # -- Abruf ----------------------------------------------------------
    @abstractmethod
    async def fetch(self, terms: list[str]) -> list[RawItem]:
        """Holt neue Beiträge für die gegebenen Suchbegriffe."""

    # -- Hilfen ---------------------------------------------------------
    async def _get(self, url: str, **kwargs) -> httpx.Response:
        headers = {"User-Agent": settings.user_agent, **kwargs.pop("headers", {})}
        resp = await self.client.get(url, headers=headers, timeout=settings.http_timeout, **kwargs)
        if resp.status_code == 429:
            raise CollectorError("Rate-Limit erreicht (HTTP 429) - Intervall erhöhen")
        if resp.status_code >= 400:
            raise CollectorError(f"HTTP {resp.status_code}: {resp.text[:180]}")
        return resp

    async def _post(self, url: str, **kwargs) -> httpx.Response:
        headers = {"User-Agent": settings.user_agent, **kwargs.pop("headers", {})}
        resp = await self.client.post(url, headers=headers, timeout=settings.http_timeout, **kwargs)
        if resp.status_code >= 400:
            raise CollectorError(f"HTTP {resp.status_code}: {resp.text[:180]}")
        return resp

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

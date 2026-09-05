"""Startbestückung: sinnvolle Suchbegriffe je Kategorie."""
from __future__ import annotations

import logging

from sqlalchemy import func, select

from .db import SessionLocal
from .enrich import CATEGORIES
from .models import Category, SearchTerm

log = logging.getLogger("netzwache.seed")

DEFAULT_TERMS: list[tuple[str, str]] = [
    # cybersecurity
    ("ransomware", "cybersecurity"),
    ("zero-day", "cybersecurity"),
    ("datenleck", "cybersecurity"),
    ("sicherheitslücke", "cybersecurity"),
    ("phishing", "cybersecurity"),
    ("cyberangriff", "cybersecurity"),
    ("CVE", "cybersecurity"),
    ("BSI", "cybersecurity"),
    # it
    ("linux", "it"),
    ("open source", "it"),
    ("kubernetes", "it"),
    ("python", "it"),
    ("selfhosted", "it"),
    ("docker", "it"),
    # nachrichten
    ("bundestag", "nachrichten"),
    ("eu kommission", "nachrichten"),
    ("inflation", "nachrichten"),
    # alltag
    ("deutsche bahn", "alltag"),
    ("deutschlandticket", "alltag"),
    ("strompreis", "alltag"),
]


async def seed_terms() -> int:
    async with SessionLocal() as s:
        count = (await s.execute(select(func.count(SearchTerm.id)))).scalar() or 0
        if count:
            return 0
        for term, cat in DEFAULT_TERMS:
            s.add(SearchTerm(term=term, category=cat, platforms=[], enabled=True))
        await s.commit()
        log.info("%d Standard-Suchbegriffe angelegt", len(DEFAULT_TERMS))
        return len(DEFAULT_TERMS)


async def seed_categories() -> dict[str, int]:
    """Legt die feste Kategorien-Tabelle an (idempotent) und gibt eine
    name->id-Zuordnung zurück, die der Scheduler beim Speichern von Posts
    braucht (siehe Engine._category_ids in scheduler.py)."""
    async with SessionLocal() as s:
        existing = {
            r.name: r.id for r in (await s.execute(select(Category))).scalars()
        }
        missing = [c for c in CATEGORIES if c not in existing]
        for name in missing:
            s.add(Category(name=name))
        if missing:
            await s.commit()
            existing = {
                r.name: r.id for r in (await s.execute(select(Category))).scalars()
            }
            log.info("%d Kategorien angelegt", len(missing))
        return existing

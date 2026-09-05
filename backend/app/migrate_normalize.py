"""Einmalige Migration: befüllt post_categories/post_tags/post_cves aus den
bestehenden categories/matched_terms/cve_ids-JSON-Spalten auf posts.

Nötig, weil die drei Tabellen neu sind (siehe models.py) - ohne diesen
Lauf würden ältere, bereits gesammelte Posts in den neuen normalisierten
Filtern (?category=, ?tag=, ?cve=) einfach fehlen, obwohl ihre JSON-Spalten
die Daten längst enthalten.

Aufruf (im backend-Ordner bzw. im laufenden Backend-Container):
    python -m app.migrate_normalize

Idempotent: kann gefahrlos mehrfach laufen (ON CONFLICT DO NOTHING /
INSERT OR IGNORE je nach Dialekt) - überspringt bereits migrierte Zeilen,
sammelt also nichts doppelt ein.
"""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select

from .db import SessionLocal, engine as db_engine, init_db
from .models import Post, PostCategory, PostCve, PostTag
from .seed import seed_categories

log = logging.getLogger("netzwache.migrate")

BATCH_SIZE = 500


def _insert_ignore(table):
    if db_engine.dialect.name == "sqlite":
        from sqlalchemy.dialects.sqlite import insert as dialect_insert
    else:
        from sqlalchemy.dialects.postgresql import insert as dialect_insert
    return dialect_insert(table).on_conflict_do_nothing()


async def run() -> tuple[int, int, int]:
    await init_db()  # legt post_categories/post_tags/post_cves an, falls noch nicht vorhanden
    category_ids = await seed_categories()

    total_cats = 0
    total_tags = 0
    total_cves = 0
    offset = 0
    async with SessionLocal() as s:
        while True:
            rows = (
                await s.execute(
                    select(Post.id, Post.categories, Post.matched_terms, Post.cve_ids)
                    .order_by(Post.id)
                    .offset(offset)
                    .limit(BATCH_SIZE)
                )
            ).all()
            if not rows:
                break

            cat_values = []
            tag_values = []
            cve_values = []
            for post_id, categories, matched_terms, cve_ids in rows:
                for cat_name in categories or []:
                    cat_id = category_ids.get(cat_name)
                    if cat_id is not None:
                        cat_values.append({"post_id": post_id, "category_id": cat_id})
                for term in matched_terms or []:
                    tag_values.append({"post_id": post_id, "tag": term})
                for cve in cve_ids or []:
                    cve_values.append({"post_id": post_id, "cve": cve})

            if cat_values:
                res = await s.execute(_insert_ignore(PostCategory.__table__).values(cat_values))
                total_cats += res.rowcount or 0  # nur tatsächlich neu eingefügte, nicht per ON CONFLICT übersprungene
            if tag_values:
                res = await s.execute(_insert_ignore(PostTag.__table__).values(tag_values))
                total_tags += res.rowcount or 0
            if cve_values:
                res = await s.execute(_insert_ignore(PostCve.__table__).values(cve_values))
                total_cves += res.rowcount or 0
            await s.commit()

            log.info("verarbeitet: %d Posts (offset %d)", len(rows), offset)
            offset += BATCH_SIZE

    return total_cats, total_tags, total_cves


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(message)s")
    cats, tags, cves = asyncio.run(run())
    print(
        f"Fertig: {cats} Kategorie-Zuordnungen, {tags} Tag-Zuordnungen, {cves} CVE-Zuordnungen "
        "eingefügt (bereits vorhandene wurden übersprungen)."
    )


if __name__ == "__main__":
    main()

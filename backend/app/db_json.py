"""Dialektabhängige Helfer, die keine Entsprechung im portablen ORM-Modell
haben: Abfragen gegen die offene JSON-Array-Spalte `keywords` (cve_ids und
categories/matched_terms haben eigene normalisierte Tabellen, siehe
models.py) und Volltextsuche.

keywords bleibt als JSON, weil es offenes Vokabular ist (jeder Text erzeugt
andere Werte) - eine eigene Tabelle dafür wäre nur eine deutlich größere
Version derselben JSON-Array-Suche. Die Spalte ist bewusst generisches JSON
(siehe models.py), damit auch SQLite (Dev/Tests) funktioniert - das heißt
aber, dass Postgres' bequeme jsonb-Operatoren (@>, ?) nicht direkt zur
Verfügung stehen (die brauchen jsonb, nicht json) und SQLite eigene
JSON1-Funktionen benutzt.

Die Volltextsuche nutzt auf Postgres die generierte `search_vector`-Spalte
(tsvector + GIN-Index, siehe db.py::init_db) - die existiert absichtlich
nicht im SQLAlchemy-Modell, weil SQLite mit `GENERATED ALWAYS AS (...)
STORED` + tsvector-Funktionen nichts anfangen kann. SQLite fällt auf die
bisherige LIKE-Suche zurück (langsamer, aber portabel).

Dieses Modul kapselt den Dialekt-Unterschied, damit die Routen selbst
dialektfrei bleiben.
"""
from __future__ import annotations

from sqlalchemy import false, func, or_, text
from sqlalchemy.engine import Dialect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ClauseElement

from .enrich import pg_term_pattern
from .models import Post


_TERM_HAYSTACK = (
    "(coalesce(posts.title,'') || ' ' || coalesce(posts.text,'') || ' ' || "
    "coalesce(posts.author,'') || ' ' || coalesce(posts.source,''))"
)


def term_match_clause(dialect: Dialect, term: str) -> ClauseElement:
    """WHERE-Ausdruck für ?term= : trifft, wenn der Suchbegriff nach der
    gemeinsamen Trefferdefinition (siehe enrich.py: Wortanfang, deutsche
    Endungen, Titel+Text+Autor+Quelle) im Beitrag vorkommt. Bewusst KEINE
    Stammform-Volltextsuche wie ?q= - die lieferte für dieselben Daten andere
    Zahlen als Tagging und Fokus-Modus (z.B. "eu kommission" 118 statt 2
    Treffern, "selfhosted" 11 statt 136)."""
    if dialect.name == "sqlite":
        return text(f"nw_term_match({_TERM_HAYSTACK}, :term) = 1").bindparams(term=term)
    pattern = pg_term_pattern(term)
    if pattern is None:
        return false()
    return text(f"{_TERM_HAYSTACK} ~* :pat").bindparams(pat=pattern)


def text_search_clause(dialect: Dialect, q: str) -> ClauseElement:
    """WHERE-Ausdruck für die Volltextsuche (?q=) - auf Postgres über den
    tsvector-Index (schnell, wortbasiert, auch bei viel Daten), auf SQLite
    über LIKE (portabel, aber ein voller Tabellenscan)."""
    if dialect.name == "sqlite":
        like = f"%{q.lower()}%"
        return or_(
            func.lower(Post.text).like(like),
            func.lower(Post.title).like(like),
            func.lower(Post.author).like(like),
            func.lower(Post.source).like(like),
        )
    return text("posts.search_vector @@ websearch_to_tsquery('german', :qtext)").bindparams(qtext=q)


async def json_array_top_counts(
    session: AsyncSession,
    dialect: Dialect,
    column_name: str,
    limit: int,
    max_per_row: int | None = None,
) -> list[tuple[str, int]]:
    """Zählt Vorkommen einzelner Elemente über die JSON-Array-Spalte
    `column_name` hinweg, aggregiert per SQL (GROUP BY/COUNT) über die
    GESAMTE Tabelle - keine Vorauswahl von "letzten N Posts" in Python.

    `max_per_row` begrenzt optional, wie viele Elemente pro Zeile mitzählen
    (z.B. nur die ersten 5 Keywords eines Posts, damit ein einzelner Post
    mit vielen Keywords die Rangliste nicht dominiert)."""
    if dialect.name == "sqlite":
        where = "WHERE je.key < :max_per_row" if max_per_row is not None else ""
        sql = text(
            f"""
            SELECT je.value AS val, COUNT(*) AS n
            FROM posts, json_each(posts.{column_name}) je
            {where}
            GROUP BY je.value
            ORDER BY n DESC
            LIMIT :limit
            """
        )
    else:
        where = "WHERE ord <= :max_per_row" if max_per_row is not None else ""
        sql = text(
            f"""
            SELECT val, COUNT(*) AS n
            FROM posts, jsonb_array_elements_text(posts.{column_name}::jsonb) WITH ORDINALITY AS t(val, ord)
            {where}
            GROUP BY val
            ORDER BY n DESC
            LIMIT :limit
            """
        )
    params: dict[str, object] = {"limit": limit}
    if max_per_row is not None:
        params["max_per_row"] = max_per_row
    rows = (await session.execute(sql, params)).all()
    return [(r[0], r[1]) for r in rows]

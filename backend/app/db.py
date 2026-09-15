"""Datenbank-Session-Handling."""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .config import settings
from .models import Base

log = logging.getLogger("netzwache.db")

engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
    future=True,
)

# SQLite ignoriert FOREIGN KEY-Constraints (u.a. ON DELETE CASCADE) ohne
# diese Pragma pro Verbindung - ohne sie blieben gelöschte Posts' Zeilen in
# post_categories/post_tags als Leichen zurück (SQLite ist nur der Dev/Test-
# Fallback, siehe models.py; Postgres erzwingt Foreign Keys ohnehin immer).
if engine.dialect.name == "sqlite":

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # create_all legt neue Tabellen/Indizes nur an, wenn die Tabelle noch
        # nicht existiert - für die schon laufende posts-Tabelle müssen neu
        # hinzugekommene Indizes (source, severity) explizit nachgezogen
        # werden. IF NOT EXISTS macht das für frische Installationen zum
        # No-op (create_all hat sie dort schon über __table_args__ angelegt).
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_posts_source ON posts (source)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_posts_severity ON posts (severity)"))

        if engine.dialect.name != "sqlite":
            # Echte Volltextsuche (Postgres-spezifisch, siehe db_json.py) -
            # SQLite hat kein äquivalentes eingebautes Feature und bleibt
            # beim bisherigen LIKE-Fallback. Generated column hält sich
            # selbst aktuell (kein Python-Code muss sie pflegen) - ABER nur
            # für ihre eigene Definition: ein Post, bei dem der Suchbegriff
            # nur in author/source steht (z.B. Quelle "BSI CERT-Bund" bei
            # Suche nach "BSI"), war für /api/posts?q= unauffindbar, weil die
            # Spalte ursprünglich nur title+text indizierte. "ADD COLUMN IF
            # NOT EXISTS" reicht hier nicht mehr aus - eine schon bestehende
            # Spalte mit der alten (zu engen) Definition bleibt sonst für
            # immer stehen. Deshalb einmalig prüfen und bei Bedarf neu
            # anlegen (billig bei den hier üblichen Datenmengen).
            needs_migration = (
                await conn.execute(
                    text(
                        "SELECT 1 FROM information_schema.columns "
                        "WHERE table_name = 'posts' AND column_name = 'search_vector' "
                        "AND generation_expression NOT ILIKE '%author%'"
                    )
                )
            ).first() is not None
            if needs_migration:
                log.info("Erweitere search_vector um author/source - einmalige Migration …")
                await conn.execute(text("DROP INDEX IF EXISTS ix_posts_search_vector"))
                await conn.execute(text("ALTER TABLE posts DROP COLUMN IF EXISTS search_vector"))
            await conn.execute(
                text(
                    "ALTER TABLE posts ADD COLUMN IF NOT EXISTS search_vector tsvector "
                    "GENERATED ALWAYS AS (to_tsvector('german', "
                    "coalesce(title, '') || ' ' || coalesce(text, '') || ' ' || "
                    "coalesce(author, '') || ' ' || coalesce(source, ''))) STORED"
                )
            )
            await conn.execute(
                text("CREATE INDEX IF NOT EXISTS ix_posts_search_vector ON posts USING GIN (search_vector)")
            )

            # --- Datenformat v2 (siehe README, "Version 1 vs. Version 2") ---
            # Nur nullable Spalten, kein Backfill, keine API-Aufrufe für
            # Bestandsdaten - create_all() legt sie für frische Installationen
            # schon über das Modell an, hier geht es nur um die schon
            # laufende posts-Tabelle mit ~96k Bestandszeilen.
            #
            # data_version bekommt bewusst einen echten Spalten-Default (1)
            # statt nur NULL zu bleiben: "ADD COLUMN ... DEFAULT <Konstante>"
            # ist ab Postgres 11 eine reine Metadaten-Operation (kein
            # Tabellen-Rewrite, keine lange exklusive Sperre), obwohl davon
            # alle Bestandszeilen betroffen sind - Version 2 wird trotzdem nie
            # rückwirkend vergeben, das setzt ausschließlich scheduler.py::
            # _store() für tatsächlich neu gesammelte Beiträge.
            await conn.execute(
                text("ALTER TABLE posts ADD COLUMN IF NOT EXISTS data_version INTEGER DEFAULT 1")
            )
            for column_sql in (
                "content_type VARCHAR(32)",
                "content_status VARCHAR(16)",
                "summary TEXT",
                "content_full TEXT",
                "canonical_url TEXT",
                "collector_mode VARCHAR(16)",
                "engagement_collected_at TIMESTAMPTZ",
                "media JSON",
                "raw_payload JSON",
            ):
                await conn.execute(text(f"ALTER TABLE posts ADD COLUMN IF NOT EXISTS {column_sql}"))


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session

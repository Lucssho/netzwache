"""Datenbank-Session-Handling."""
from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .config import settings
from .models import Base

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
            # selbst aktuell (kein Python-Code muss sie pflegen).
            await conn.execute(
                text(
                    "ALTER TABLE posts ADD COLUMN IF NOT EXISTS search_vector tsvector "
                    "GENERATED ALWAYS AS (to_tsvector('german', "
                    "coalesce(title, '') || ' ' || coalesce(text, ''))) STORED"
                )
            )
            await conn.execute(
                text("CREATE INDEX IF NOT EXISTS ix_posts_search_vector ON posts USING GIN (search_vector)")
            )


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session

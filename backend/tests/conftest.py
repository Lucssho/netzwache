"""Test-Fixtures: SQLite statt Postgres, In-Memory-Dedup statt Redis, kein Netz."""
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
import pytest_asyncio

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_netzwache.db")
os.environ.setdefault("REDIS_URL", "redis://127.0.0.1:1/0")  # bewusst tot -> Memory-Fallback
os.environ.setdefault("TICK_SECONDS", "3600")                # Scheduler stört den Test nicht


@pytest.fixture(scope="session", autouse=True)
def clean_db_file():
    db = ROOT / "test_netzwache.db"
    if db.exists():
        db.unlink()
    yield
    if db.exists():
        db.unlink()


@pytest_asyncio.fixture
async def app_client():
    import httpx
    from httpx import ASGITransport

    from app.main import app

    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # lifespan manuell fahren, damit init_db/seed/engine laufen
        async with app.router.lifespan_context(app):
            yield client


@pytest_asyncio.fixture
async def seed_posts():
    from app.collectors.base import RawItem
    from app.scheduler import engine

    async def _seed():
        now = datetime.now(timezone.utc)
        items = [
            RawItem(
                platform="bluesky",
                external_id="at://x/1",
                text="Ransomware-Angriff auf Klinik, CVE-2026-1111 wird aktiv ausgenutzt",
                author="Alice",
                author_handle="alice.bsky.social",
                url="https://bsky.app/x/1",
                created_at=now,
            ),
            RawItem(
                platform="reddit",
                external_id="t3_1",
                title="Linux Kernel 7.0",
                text="Der neue Kernel bringt bessere Docker-Unterstützung",
                author="bob",
                source="r/linux",
                created_at=now,
            ),
            RawItem(
                platform="news",
                external_id="news:1",
                title="Bundestag beschließt Gesetz",
                text="Die Regierung hat heute im Bundestag ein neues Gesetz beschlossen",
                source="tagesschau",
                category_hint="nachrichten",
                created_at=now,
            ),
            # exaktes Duplikat des ersten Eintrags -> muss verworfen werden
            RawItem(
                platform="bluesky",
                external_id="at://x/1",
                text="Ransomware-Angriff auf Klinik, CVE-2026-1111 wird aktiv ausgenutzt",
                author="Alice",
                created_at=now,
            ),
        ]
        return await engine._store(items, ["ransomware", "linux"])

    return _seed

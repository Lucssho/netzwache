"""NETZWACHE - Backend-Einstiegspunkt."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import desc, select

from .api import router
from .config import settings
from .db import SessionLocal, init_db
from .dedup import dedup
from .hub import hub
from .models import EventLog, Post, SourceState
from .scheduler import engine
from .seed import seed_terms

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-7s | %(name)-28s | %(message)s",
)
log = logging.getLogger("netzwache")

BANNER = r"""
 _   _ _____ _____ _______        __    _    ____ _   _ _____
| \ | | ____|_   _|__  /\ \      / /_ _| |  / ___| | | | ____|
|  \| |  _|   | |   / /  \ \ /\ / / _` | | | |   | |_| |  _|
| |\  | |___  | |  / /_   \ V  V / (_| | | | |___|  _  | |___
|_| \_|_____| |_| /____|   \_/\_/ \__,_|_|  \____|_| |_|_____|
   Open-Source Lagebild:  Bluesky · Reddit · Google News · X · Facebook · News
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(BANNER)
    await init_db()
    await dedup.connect()
    created = await seed_terms()
    if created:
        log.info("Seed: %d Suchbegriffe angelegt", created)
    await engine.start()
    try:
        yield
    finally:
        await engine.stop()
        await dedup.close()
        log.info("NETZWACHE beendet")


app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    description="Plattformübergreifende Textsammlung mit Live-Dashboard",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/")
async def root() -> dict:
    return {
        "app": settings.app_name,
        "version": settings.version,
        "docs": "/docs",
        "websocket": "/ws",
    }


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    """Live-Stream: schickt beim Verbinden einen Snapshot, danach Deltas."""
    await hub.connect(ws)
    try:
        async with SessionLocal() as s:
            posts = (
                await s.execute(select(Post).order_by(desc(Post.collected_at)).limit(60))
            ).scalars().all()
            sources = (await s.execute(select(SourceState))).scalars().all()
            logs = (
                await s.execute(select(EventLog).order_by(desc(EventLog.ts)).limit(25))
            ).scalars().all()
        await ws.send_json(
            {
                "event": "snapshot",
                "data": {
                    "posts": [p.to_dict() for p in reversed(posts)],
                    "sources": [x.to_dict() for x in sources],
                    "log": [x.to_dict() for x in reversed(logs)],
                    "tick_seconds": settings.tick_seconds,
                },
            }
        )
        while True:
            # Client-Pings entgegennehmen; hält die Verbindung offen
            try:
                await asyncio.wait_for(ws.receive_text(), timeout=45)
            except asyncio.TimeoutError:
                await ws.send_json({"event": "ping", "data": {}})
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # pragma: no cover
        log.debug("WS-Fehler: %s", exc)
    finally:
        await hub.disconnect(ws)

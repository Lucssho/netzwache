"""Duplikat-Erkennung über Redis (schnell) mit DB als Rückfallebene."""
from __future__ import annotations

import logging
import time
from collections.abc import Iterable

import redis.asyncio as aioredis

from .config import settings

log = logging.getLogger("netzwache.dedup")

_KEY = "nw:seen:"
_RECONNECT_AFTER_S = 30.0


class Dedup:
    def __init__(self) -> None:
        self._client: aioredis.Redis | None = None
        self._memory: set[str] = set()
        self.backend = "memory"
        self._next_reconnect = 0.0

    async def connect(self) -> None:
        try:
            client = aioredis.from_url(settings.redis_url, decode_responses=True)
            await client.ping()
            self._client = client
            self.backend = "redis"
            log.info("Dedup nutzt Redis: %s", settings.redis_url)
        except Exception as exc:  # pragma: no cover - Umgebungsabhängig
            self._client = None
            self.backend = "memory"
            self._next_reconnect = time.monotonic() + _RECONNECT_AFTER_S
            log.warning("Redis nicht erreichbar (%s) - nutze In-Memory-Dedup", exc)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _maybe_reconnect(self) -> None:
        """Nach einem Redis-Ausfall (z.B. Neustart) wieder auf Redis umschalten,
        statt bis zum nächsten Backend-Neustart im reinen Memory-Modus zu
        bleiben - der geht bei jedem Neustart verloren und lässt bereits
        gesehene Beiträge wieder als "neu" durchgehen."""
        if self._client is not None or time.monotonic() < self._next_reconnect:
            return
        self._next_reconnect = time.monotonic() + _RECONNECT_AFTER_S
        try:
            client = aioredis.from_url(settings.redis_url, decode_responses=True)
            await client.ping()
        except Exception:
            return
        self._client = client
        self.backend = "redis"
        log.info("Dedup: Redis wieder erreichbar - wechsle zurück auf Redis")

    async def seen(self, key: str) -> bool:
        """True, wenn der Hash bereits bekannt war. Markiert ihn sonst als gesehen."""
        await self._maybe_reconnect()
        if self._client is not None:
            try:
                added = await self._client.set(
                    _KEY + key, "1", ex=settings.dedup_ttl_days * 86400, nx=True
                )
                return added is None
            except Exception as exc:  # pragma: no cover
                log.warning("Redis-Fehler, falle auf Memory zurück: %s", exc)
                self._client = None
                self.backend = "memory"
                self._next_reconnect = time.monotonic() + _RECONNECT_AFTER_S
        if key in self._memory:
            return True
        self._memory.add(key)
        if len(self._memory) > 200_000:
            self._memory = set(list(self._memory)[-100_000:])
        return False

    async def forget(self, key: str) -> None:
        if self._client is not None:
            try:
                await self._client.delete(_KEY + key)
            except Exception:
                pass
        self._memory.discard(key)

    async def forget_many(self, keys: Iterable[str]) -> None:
        """Gibt mehrere Schlüssel auf einmal frei (siehe Engine._store: ein
        nicht gespeicherter Post muss ALLE seine Schlüssel wieder freigeben)."""
        keys = list(keys)
        if not keys:
            return
        if self._client is not None:
            try:
                await self._client.delete(*[_KEY + k for k in keys])
            except Exception:
                pass
        self._memory.difference_update(keys)


dedup = Dedup()

"""Duplikat-Erkennung über Redis (schnell) mit DB als Rückfallebene."""
from __future__ import annotations

import logging

import redis.asyncio as aioredis

from .config import settings

log = logging.getLogger("netzwache.dedup")

_KEY = "nw:seen:"


class Dedup:
    def __init__(self) -> None:
        self._client: aioredis.Redis | None = None
        self._memory: set[str] = set()
        self.backend = "memory"

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
            log.warning("Redis nicht erreichbar (%s) - nutze In-Memory-Dedup", exc)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def seen(self, key: str) -> bool:
        """True, wenn der Hash bereits bekannt war. Markiert ihn sonst als gesehen."""
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


dedup = Dedup()

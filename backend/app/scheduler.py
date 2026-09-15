"""Sammel-Engine.

Ein Tick alle TICK_SECONDS (Standard 10s). Pro Tick wird geprüft, welche
Collector ihr eigenes Intervall erreicht haben - so bleibt der 10s-Puls
erhalten, ohne die Rate-Limits der Plattformen zu verletzen.
"""
from __future__ import annotations

import asyncio
import logging
import math
import multiprocessing
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import delete, func, select, text, update

from .collectors import COLLECTOR_CLASSES, BaseCollector, CollectorError, RawItem
from .config import settings
from .db import SessionLocal
from .db import engine as db_engine
from .dedup import dedup
from .enrich import content_hash, enrich, normalize, text_fingerprint
from .hub import hub
from .models import EventLog, Post, PostCategory, PostCve, PostTag, SearchTerm, SourceState, UiSetting
from .payload import sanitize_raw_payload
from .seed import seed_categories

log = logging.getLogger("netzwache.scheduler")


def _enrich_batch(entries: list[tuple[str, str, str]], terms: list[str]) -> list[dict]:
    """Reichert mehrere Items in einem Rutsch an - läuft in einem separaten
    Prozess (ProcessPoolExecutor), damit die CPU-lastige Regex-/Keyword-Arbeit
    in enrich.py nicht um den GIL mit dem Event-Loop-Thread konkurriert. Ein
    Thread (asyncio.to_thread) hätte hier nicht gereicht: CPU-lastige Arbeit
    hält den GIL fast durchgehend, wodurch der Event-Loop-Thread trotzdem
    kaum zum Zug kommt - nur ein echter Prozess umgeht das."""
    return [enrich(text, title, hint, terms) for text, title, hint in entries]


# "spawn" statt "fork": plattformunabhängig (Tests laufen auch unter Windows)
# und vermeidet, dass Worker-Prozesse bereits offene DB-/Redis-Verbindungen
# des Elternprozesses per fork() erben. Als Modul-Singleton angelegt, damit
# nicht bei jedem Engine.start()/stop()-Zyklus (z.B. in Tests) ein neuer
# Prozess-Pool auf- und abgebaut wird.
_enrich_pool = ProcessPoolExecutor(max_workers=2, mp_context=multiprocessing.get_context("spawn"))


class Engine:
    def __init__(self) -> None:
        self.client: httpx.AsyncClient | None = None
        self.collectors: dict[str, BaseCollector] = {}
        self._task: asyncio.Task | None = None
        self._running = False
        self._last_run: dict[str, float] = {}
        self._lock = asyncio.Lock()
        self.started_at = datetime.now(timezone.utc)
        self.tick_count = 0
        self.collected_session = 0
        self._last_cleanup: float | None = None
        self._category_ids: dict[str, int] = {}

    # ------------------------------------------------------------------
    async def start(self) -> None:
        self.client = httpx.AsyncClient(
            follow_redirects=True,
            headers={"User-Agent": settings.user_agent},
            timeout=settings.http_timeout,
        )
        self.collectors = {c.name: c(self.client) for c in COLLECTOR_CLASSES}
        await self._sync_source_state()
        self._category_ids = await seed_categories()
        self._running = True
        self._task = asyncio.create_task(self._loop(), name="netzwache-engine")
        log.info("Engine gestartet: %s Collector, Tick %ss",
                 len(self.collectors), settings.tick_seconds)

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self.client:
            await self.client.aclose()

    # ------------------------------------------------------------------
    async def _sync_source_state(self) -> None:
        """Legt für jeden registrierten Collector eine Statuszeile an."""
        async with SessionLocal() as s:
            existing = {r.name for r in (await s.execute(select(SourceState))).scalars()}
            for name, col in self.collectors.items():
                ok, detail = col.available()
                if name in existing:
                    await s.execute(
                        update(SourceState)
                        .where(SourceState.name == name)
                        .values(
                            label=col.label,
                            platform=col.platform,
                            detail=detail,
                            interval_seconds=col.default_interval,
                            status="idle" if ok else "disabled",
                        )
                    )
                else:
                    s.add(
                        SourceState(
                            name=name,
                            platform=col.platform,
                            label=col.label,
                            detail=detail,
                            enabled=True,
                            interval_seconds=col.default_interval,
                            status="idle" if ok else "disabled",
                        )
                    )
            await s.commit()

    async def _active_terms(self) -> list[SearchTerm]:
        async with SessionLocal() as s:
            rows = (
                await s.execute(select(SearchTerm).where(SearchTerm.enabled.is_(True)))
            ).scalars().all()
            return list(rows)

    # ------------------------------------------------------------------
    async def _loop(self) -> None:
        # kleiner Vorlauf, damit DB/Redis sicher oben sind
        await asyncio.sleep(2)
        while self._running:
            started = time.perf_counter()
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # pragma: no cover
                log.exception("Tick fehlgeschlagen: %s", exc)
            elapsed = time.perf_counter() - started
            await asyncio.sleep(max(1.0, settings.tick_seconds - elapsed))

    async def tick(self, force: list[str] | None = None) -> dict:
        """Ein Sammel-Durchlauf. force=[collector-namen] ignoriert Intervalle."""
        async with self._lock:
            self.tick_count += 1
            now = time.monotonic()
            await self._maybe_cleanup(now)
            terms_rows = await self._active_terms()
            all_terms = [t.term for t in terms_rows]

            async with SessionLocal() as s:
                states = {
                    r.name: r for r in (await s.execute(select(SourceState))).scalars()
                }

            due: list[str] = []
            for name, col in self.collectors.items():
                st = states.get(name)
                if st and not st.enabled:
                    continue
                ok, _ = col.available()
                if not ok:
                    continue
                if force and name not in force:
                    continue
                interval = st.interval_seconds if st else col.default_interval
                if force or (now - self._last_run.get(name, 0.0)) >= interval:
                    due.append(name)

            if not due:
                await hub.broadcast("tick", {"tick": self.tick_count, "due": [], "ts": _iso()})
                return {"ran": [], "new": 0}

            results = await asyncio.gather(
                *(self._run_collector(name, all_terms) for name in due),
                return_exceptions=True,
            )
            total_new = sum(r for r in results if isinstance(r, int))
            await hub.broadcast(
                "tick",
                {"tick": self.tick_count, "due": due, "new": total_new, "ts": _iso()},
            )
            return {"ran": due, "new": total_new}

    async def _maybe_cleanup(self, now: float) -> None:
        """Retention-Räumung (settings.retention_days) automatisch im Takt von
        settings.cleanup_interval_seconds - lief vorher nur, wenn jemand
        manuell POST /api/maintenance/cleanup aufgerufen hat. Läuft beim
        allerersten Tick sofort (self._last_cleanup ist noch None), danach im
        konfigurierten Intervall."""
        if self._last_cleanup is not None and (now - self._last_cleanup) < settings.cleanup_interval_seconds:
            return
        self._last_cleanup = now
        removed = await self.cleanup()
        if removed:
            await self._log(
                "info", "core", f"{removed} Beiträge älter als {settings.retention_days} Tage entfernt"
            )

    # ------------------------------------------------------------------
    async def _run_collector(self, name: str, terms: list[str]) -> int:
        col = self.collectors[name]
        self._last_run[name] = time.monotonic()
        t0 = time.perf_counter()
        try:
            items = await col.fetch(terms)
        except CollectorError as exc:
            await self._mark_error(name, str(exc))
            return 0
        except Exception as exc:  # pragma: no cover
            log.exception("Collector %s abgestürzt", name)
            await self._mark_error(name, f"{type(exc).__name__}: {exc}")
            return 0

        duration_ms = (time.perf_counter() - t0) * 1000
        stored = await self._store(items, terms)
        await self._mark_ok(name, len(stored), duration_ms)
        if stored:
            self.collected_session += len(stored)
            await hub.broadcast("posts", [p for p in stored])
            await self._log(
                "info", name, f"{len(stored)} neue Beiträge ({len(items)} geprüft)"
            )
            await self._enforce_storage_limits()
        return len(stored)

    async def _enforce_storage_limits(self) -> None:
        """Postgres (Produktion): Größenlimit (settings.max_posts_size_gb) -
        SQLite (Dev/Tests) kennt kein pg_total_relation_size und bleibt beim
        einfacheren Zeilen-Limit (settings.max_posts), das für die dortigen
        Datenmengen ohnehin ausreicht."""
        if db_engine.dialect.name == "sqlite":
            await self._enforce_post_cap()
        else:
            await self._enforce_size_cap()

    async def _enforce_post_cap(self) -> None:
        """Harte Obergrenze (settings.max_posts): wird sie überschritten,
        fallen die ältesten Posts (nach collected_at) zuerst raus - unabhängig
        von retention_days, das nur zeitbasiert aufräumt und ohnehin nicht
        automatisch läuft."""
        if not settings.max_posts:
            return
        async with SessionLocal() as s:
            total = (await s.execute(select(func.count(Post.id)))).scalar_one()
            overflow = total - settings.max_posts
            if overflow <= 0:
                return
            oldest_ids = select(Post.id).order_by(Post.collected_at.asc()).limit(overflow)
            res = await s.execute(delete(Post).where(Post.id.in_(oldest_ids)))
            await s.commit()
            removed = res.rowcount or 0
        if removed:
            await self._log(
                "info", "core", f"{removed} älteste Beiträge entfernt (Limit {settings.max_posts})"
            )

    async def _effective_size_limits(self, s) -> tuple[float, float]:
        """Liest max_posts_size_gb/posts_trim_chunk_mb aus ui_settings (per
        PUT /api/settings admin-änderbar, wirkt sofort ohne Neustart) - fällt
        auf die .env-Werte zurück, solange niemand sie über die Oberfläche
        geändert hat."""
        rows = {
            r.key: r.value
            for r in (
                await s.execute(
                    select(UiSetting).where(
                        UiSetting.key.in_(["max_posts_size_gb", "posts_trim_chunk_mb"])
                    )
                )
            ).scalars()
        }
        try:
            max_gb = float(rows["max_posts_size_gb"])
        except (KeyError, ValueError):
            max_gb = settings.max_posts_size_gb
        try:
            chunk_mb = float(rows["posts_trim_chunk_mb"])
        except (KeyError, ValueError):
            chunk_mb = settings.posts_trim_chunk_mb
        return max_gb, chunk_mb

    async def _enforce_size_cap(self) -> None:
        """Harte Größenobergrenze (settings.max_posts_size_gb) für die
        posts-Tabelle inkl. ihrer eigenen Indizes (pg_total_relation_size -
        Postgres-spezifisch, siehe _enforce_storage_limits).

        Löscht bei Überschreitung nur ein Stück der ältesten Posts
        (settings.posts_trim_chunk_mb), nicht alles auf einen Schlag - hält
        jeden einzelnen Lauf schnell und günstig. Wird das Limit später
        stark gesenkt, holt das mehrere Sammel-Läufe in kleinen Schritten
        nach, statt einmalig einen großen Batch zu löschen.

        Wichtig: DELETE gibt den Plattenplatz nicht an das Betriebssystem
        zurück (kein VACUUM FULL, das die Tabelle exklusiv sperren würde) -
        er wird nur für künftige INSERTs wiederverwendet. Die Datei auf der
        Platte wächst dadurch bis zum Limit und bleibt danach etwa auf der
        einmal erreichten Größe stehen, schrumpft aber nicht sichtbar - auch
        nicht, wenn das Limit nachträglich gesenkt wird."""
        async with SessionLocal() as s:
            max_gb, chunk_mb = await self._effective_size_limits(s)
            max_bytes = max_gb * 1024**3
            if not max_bytes:
                return
            total_size, total_rows = (
                await s.execute(
                    text("SELECT pg_total_relation_size('posts'), (SELECT count(*) FROM posts)")
                )
            ).one()
            if total_size <= max_bytes or not total_rows:
                return
            avg_row_bytes = total_size / total_rows
            chunk_bytes = chunk_mb * 1024**2
            rows_to_delete = max(1, math.ceil(chunk_bytes / avg_row_bytes))
            oldest_ids = select(Post.id).order_by(Post.collected_at.asc()).limit(rows_to_delete)
            res = await s.execute(delete(Post).where(Post.id.in_(oldest_ids)))
            await s.commit()
            removed = res.rowcount or 0
        if removed:
            await self._log(
                "info",
                "core",
                f"{removed} älteste Beiträge entfernt (~{chunk_mb:.0f}MB, Limit {max_gb:.0f}GB erreicht)",
            )

    async def _store(self, items: list[RawItem], terms: list[str]) -> list[dict]:
        """Dedupliziert, reichert an und schreibt in die DB.

        Dedup (Redis) und Anreicherung (CPU-lastig: Regex/Keyword-Matching in
        enrich.py) laufen bewusst OHNE offene DB-Session - eine gepoolte
        Connection soll nur für die eigentlichen Schreibzugriffe belegt sein,
        nicht während des ganzen Laufs blockiert werden. Die Anreicherung
        selbst läuft gebündelt in einem separaten Prozess (ProcessPoolExecutor,
        siehe _enrich_pool), nicht nur einem Thread: CPU-lastige Arbeit hält
        den GIL fast durchgehend, ein Thread hätte den Event-Loop also kaum
        entlastet - nur ein echter Prozess umgeht das.
        """
        out: list[dict] = []
        if not items:
            return out

        # Phase 1: Dedup (kein DB-Session nötig - dedup läuft über Redis)
        candidates: list[tuple[RawItem, str, str]] = []
        for it in items:
            text = normalize(it.text)
            if not text and not it.title:
                continue
            h = content_hash(it.platform, it.external_id, text)
            if await dedup.seen(h):
                continue
            fp = text_fingerprint(f"{it.title} {text}")
            if await dedup.seen(f"fp:{fp}"):
                continue
            candidates.append((it, text, h))

        if not candidates:
            return out

        # Phase 2: Anreicherung - CPU-lastig, gebündelt in einem separaten Prozess
        loop = asyncio.get_running_loop()
        metas = await loop.run_in_executor(
            _enrich_pool,
            _enrich_batch,
            [(text, it.title, it.category_hint) for it, text, _ in candidates],
            terms,
        )

        # Phase 3: DB-Session nur für den eigentlichen Schreibzugriff öffnen
        async with SessionLocal() as s:
            for (it, text, h), meta in zip(candidates, metas):
                # Datenformat v2 (siehe README) - nur für Beiträge, die HIER,
                # jetzt, tatsächlich neu gesammelt werden. Bestandsdaten
                # (data_version NULL/1) werden nie rückwirkend angefasst -
                # dieser Codepfad läuft ausschließlich für frisch abgerufene
                # RawItems aus den Collectoren.
                post = Post(
                    platform=it.platform,
                    source=it.source or it.platform,
                    external_id=it.external_id[:255],
                    content_hash=h,
                    author=(it.author or "")[:255],
                    author_handle=(it.author_handle or "")[:255],
                    title=it.title,
                    text=text,
                    url=it.url,
                    lang=(it.lang or "")[:8],
                    created_at=it.created_at,
                    collected_at=datetime.now(timezone.utc),
                    engagement=it.engagement,
                    # Zeitpunkt DER BEOBACHTUNG, nicht irgendein späterer
                    # Abgleich - wir tracken Engagement nur als Momentaufnahme
                    # zum Sammelzeitpunkt, keine laufende Nachverfolgung (siehe
                    # README). Leer, wenn der Collector gar keine
                    # Engagement-Werte geliefert hat (nicht 0/jetzt vortäuschen).
                    engagement_collected_at=datetime.now(timezone.utc) if it.engagement else None,
                    raw=it.raw,
                    data_version=2,
                    content_type=it.content_type or None,
                    content_status=it.content_status or None,
                    summary=it.summary or None,
                    content_full=it.content_full or None,
                    canonical_url=it.canonical_url or None,
                    collector_mode=it.collector_mode or None,
                    media=it.media or None,
                    raw_payload=sanitize_raw_payload(it.raw_payload, settings.raw_payload_max_bytes)
                    if it.raw_payload
                    else None,
                    **meta,
                )
                # Savepoint: ein kollidierender Datensatz darf die anderen
                # Einträge desselben Laufs nicht mit zurückrollen.
                savepoint = await s.begin_nested()
                s.add(post)
                try:
                    await s.flush()  # post.id wird gebraucht, um die Zuordnungen zu verknüpfen
                    for cat_name in meta["categories"]:
                        cat_id = self._category_ids.get(cat_name)
                        if cat_id is not None:
                            s.add(PostCategory(post_id=post.id, category_id=cat_id))
                    for term in meta["matched_terms"]:
                        s.add(PostTag(post_id=post.id, tag=term))
                    for cve in meta["cve_ids"]:
                        s.add(PostCve(post_id=post.id, cve=cve))
                    await s.flush()
                    await savepoint.commit()
                except Exception as exc:
                    await savepoint.rollback()
                    await dedup.forget(h)
                    log.debug("Insert verworfen (%s): %s", it.external_id, exc)
                    continue
                out.append(post.to_dict())

            # Trefferzähler der Suchbegriffe fortschreiben
            if out:
                hits: dict[str, int] = {}
                for p in out:
                    for t in p["matched_terms"]:
                        hits[t] = hits.get(t, 0) + 1
                for term, n in hits.items():
                    await s.execute(
                        update(SearchTerm)
                        .where(SearchTerm.term == term)
                        .values(hits=SearchTerm.hits + n, last_hit_at=datetime.now(timezone.utc))
                    )
            await s.commit()
        return out

    # ------------------------------------------------------------------
    async def _mark_ok(self, name: str, count: int, duration_ms: float) -> None:
        now = datetime.now(timezone.utc)
        async with SessionLocal() as s:
            await s.execute(
                update(SourceState)
                .where(SourceState.name == name)
                .values(
                    status="ok",
                    last_run_at=now,
                    last_success_at=now,
                    last_duration_ms=duration_ms,
                    items_last_run=count,
                    items_total=SourceState.items_total + count,
                    consecutive_errors=0,
                )
            )
            await s.commit()
        await self._push_sources()

    async def _mark_error(self, name: str, message: str) -> None:
        now = datetime.now(timezone.utc)
        async with SessionLocal() as s:
            await s.execute(
                update(SourceState)
                .where(SourceState.name == name)
                .values(
                    status="error",
                    last_run_at=now,
                    detail=message[:400],
                    errors_total=SourceState.errors_total + 1,
                    consecutive_errors=SourceState.consecutive_errors + 1,
                )
            )
            await s.commit()
        await self._log("error", name, message[:300])
        await self._push_sources()

    async def _push_sources(self) -> None:
        async with SessionLocal() as s:
            rows = (await s.execute(select(SourceState))).scalars().all()
            await hub.broadcast("sources", [r.to_dict() for r in rows])

    async def _log(self, level: str, source: str, message: str) -> None:
        async with SessionLocal() as s:
            entry = EventLog(level=level, source=source, message=message)
            s.add(entry)
            await s.commit()
            payload = entry.to_dict()
        await hub.broadcast("log", payload)

    # ------------------------------------------------------------------
    async def cleanup(self) -> int:
        """Löscht alte Posts und Logeinträge (Retention)."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=settings.retention_days)
        async with SessionLocal() as s:
            res = await s.execute(delete(Post).where(Post.collected_at < cutoff))
            await s.execute(
                delete(EventLog).where(
                    EventLog.ts < datetime.now(timezone.utc) - timedelta(days=3)
                )
            )
            await s.commit()
            return res.rowcount or 0

    @property
    def uptime_seconds(self) -> float:
        return (datetime.now(timezone.utc) - self.started_at).total_seconds()


def _iso() -> str:
    return datetime.now(timezone.utc).isoformat()


engine = Engine()

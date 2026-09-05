"""REST-Endpunkte von NETZWACHE."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import delete, desc, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import is_admin, require_admin, verify_admin_credentials
from ..collectors import COLLECTOR_CLASSES
from ..config import settings
from ..db import engine as db_engine, get_session
from ..dedup import dedup
from ..db_json import json_array_top_counts, text_search_clause
from ..enrich import CATEGORIES
from ..hub import hub
from ..models import Category, EventLog, Post, PostCategory, PostCve, PostTag, SearchTerm, SourceState, UiSetting
from ..scheduler import engine
from ..schemas import AdminLogin, SettingsPatch, SourcePatch, TermIn, TermPatch

router = APIRouter(prefix="/api")

DEFAULT_UI_SETTINGS: dict[str, str] = {
    "font_family": "jetbrains",   # jetbrains | fira | sfmono | menlo | inter | system
    "font_size": "13",            # px, 11..18
    "density": "comfortable",     # compact | comfortable | relaxed
    "theme": "dark",               # dark | light
}


def _mask(value: str, keep: int = 3) -> str | None:
    """Zeigt nur an, DASS ein Geheimnis gesetzt ist - nie den Wert selbst."""
    if not value:
        return None
    if len(value) <= keep:
        return "•" * len(value)
    return value[:keep] + "•" * max(3, len(value) - keep)


# ---------------------------------------------------------------- System
@router.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": settings.version,
        "uptime_seconds": round(engine.uptime_seconds, 1),
        "tick_seconds": settings.tick_seconds,
        "ticks": engine.tick_count,
        "collected_session": engine.collected_session,
        "dedup_backend": dedup.backend,
        "ws_clients": hub.count,
    }


@router.post("/auth/login")
async def login(body: AdminLogin, request: Request) -> dict:
    if not verify_admin_credentials(body.username, body.password):
        raise HTTPException(401, "Benutzername oder Passwort falsch")
    request.session["admin"] = True
    return {"authenticated": True}


@router.post("/auth/logout")
async def logout(request: Request) -> dict:
    request.session.clear()
    return {"authenticated": False}


@router.get("/auth/me")
async def whoami(request: Request) -> dict:
    return {"authenticated": is_admin(request)}


@router.get("/meta")
async def meta() -> dict:
    """Statische Infos: welche Collector existieren und was sie brauchen."""
    return {
        "categories": list(CATEGORIES),
        "platforms": [c.platform for c in COLLECTOR_CLASSES],
        "collectors": [
            {
                "name": c.name,
                "platform": c.platform,
                "label": c.label,
                "default_interval": c.default_interval,
                "setup_hint": c.setup_hint,
            }
            for c in COLLECTOR_CLASSES
        ],
    }


# ----------------------------------------------------------------- Posts
@router.get("/posts")
async def list_posts(
    limit: int = Query(60, ge=1, le=500),
    offset: int = Query(0, ge=0),
    platform: str | None = None,
    source: str | None = None,
    category: str | None = None,
    tag: str | None = None,
    cve: str | None = None,
    q: str | None = None,
    min_severity: int = Query(0, ge=0, le=100),
    since_minutes: int | None = Query(None, ge=1, le=60 * 24 * 30),
    session: AsyncSession = Depends(get_session),
) -> dict:
    stmt = select(Post)
    count_stmt = select(func.count(Post.id))

    def apply(s):
        if platform and platform != "all":
            s = s.where(Post.platform == platform)
        if source:
            s = s.where(Post.source == source)
        if category and category != "all":
            # Normalisierter Join statt JSON-Array-Suche - siehe post_categories/Category.
            s = (
                s.join(PostCategory, PostCategory.post_id == Post.id)
                .join(Category, Category.id == PostCategory.category_id)
                .where(Category.name == category)
            )
        if tag:
            # z.B. "linux" - der Suchbegriff, den der Post getroffen hat.
            s = s.join(PostTag, PostTag.post_id == Post.id).where(PostTag.tag == tag)
        if cve:
            s = s.join(PostCve, PostCve.post_id == Post.id).where(PostCve.cve == cve.upper())
        if q:
            # Postgres: echte Volltextsuche über den tsvector-Index.
            # SQLite: LIKE-Fallback (siehe db_json.py).
            s = s.where(text_search_clause(db_engine.dialect, q))
        if min_severity:
            s = s.where(Post.severity >= min_severity)
        if since_minutes:
            cutoff = datetime.now(timezone.utc) - timedelta(minutes=since_minutes)
            s = s.where(Post.collected_at >= cutoff)
        return s

    # Dieselben Filter (inkl. category) für items UND total - sonst zeigt
    # total die ungefilterte/teilgefilterte Zahl an, während items bereits
    # vollständig gefiltert sind.
    stmt, count_stmt = apply(stmt), apply(count_stmt)
    rows = (
        await session.execute(stmt.order_by(desc(Post.collected_at)).limit(limit).offset(offset))
    ).scalars().all()

    items = [r.to_dict() for r in rows]
    total = (await session.execute(count_stmt)).scalar() or 0
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/posts/{post_id}")
async def get_post(post_id: int, session: AsyncSession = Depends(get_session)) -> dict:
    row = await session.get(Post, post_id)
    if not row:
        raise HTTPException(404, "Post nicht gefunden")
    return row.to_dict()


# ----------------------------------------------------------------- Stats
@router.get("/stats")
async def stats(session: AsyncSession = Depends(get_session)) -> dict:
    total = (await session.execute(select(func.count(Post.id)))).scalar() or 0

    by_platform = {
        p: n
        for p, n in (
            await session.execute(
                select(Post.platform, func.count(Post.id)).group_by(Post.platform)
            )
        ).all()
    }

    now = datetime.now(timezone.utc)
    last_hour = (
        await session.execute(
            select(func.count(Post.id)).where(Post.collected_at >= now - timedelta(hours=1))
        )
    ).scalar() or 0
    last_5min = (
        await session.execute(
            select(func.count(Post.id)).where(Post.collected_at >= now - timedelta(minutes=5))
        )
    ).scalar() or 0

    # by_category/top_cves: echtes GROUP BY über die normalisierten
    # post_categories/post_cves-Tabellen (kein JSON-Array-Unnesting nötig).
    # top_keywords bleibt offenes Vokabular ohne eigene Tabelle und läuft
    # weiter über db_json.py.
    category_counts = dict(
        (
            await session.execute(
                select(Category.name, func.count(PostCategory.post_id))
                .join(PostCategory, PostCategory.category_id == Category.id)
                .group_by(Category.name)
            )
        ).all()
    )
    by_category = {c: category_counts.get(c, 0) for c in CATEGORIES}

    top_cves = [
        (c, n)
        for c, n in (
            await session.execute(
                select(PostCve.cve, func.count(PostCve.post_id))
                .group_by(PostCve.cve)
                .order_by(desc(func.count(PostCve.post_id)))
                .limit(10)
            )
        ).all()
    ]

    dialect = db_engine.dialect
    top_keywords = await json_array_top_counts(
        session, dialect, "keywords", limit=14, max_per_row=5
    )

    high_sev = (
        await session.execute(select(func.count(Post.id)).where(Post.severity >= 40))
    ).scalar() or 0

    # Zeitreihe: Posts pro Minute (letzte 30 Minuten)
    series_rows = (
        await session.execute(
            select(Post.collected_at).where(Post.collected_at >= now - timedelta(minutes=30))
        )
    ).scalars().all()
    buckets = [0] * 30
    for ts in series_rows:
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        idx = int((now - ts).total_seconds() // 60)
        if 0 <= idx < 30:
            buckets[29 - idx] += 1

    return {
        "total": total,
        "by_platform": by_platform,
        "by_category": by_category,
        "last_hour": last_hour,
        "last_5min": last_5min,
        "per_minute": round(last_hour / 60, 2),
        "high_severity": high_sev,
        "top_keywords": top_keywords,
        "top_cves": top_cves,
        "series": buckets,
        "uptime_seconds": round(engine.uptime_seconds, 1),
        "ticks": engine.tick_count,
    }


# --------------------------------------------------------------- Quellen
@router.get("/sources")
async def list_sources(session: AsyncSession = Depends(get_session)) -> list[dict]:
    rows = (await session.execute(select(SourceState))).scalars().all()
    hints = {c.name: c.setup_hint for c in COLLECTOR_CLASSES}
    out = []
    for r in rows:
        d = r.to_dict()
        d["setup_hint"] = hints.get(r.name, "")
        out.append(d)
    order = [c.name for c in COLLECTOR_CLASSES]
    out.sort(key=lambda d: order.index(d["name"]) if d["name"] in order else 99)
    return out


@router.patch("/sources/{name}", dependencies=[Depends(require_admin)])
async def patch_source(
    name: str, patch: SourcePatch, session: AsyncSession = Depends(get_session)
) -> dict:
    row = await session.get(SourceState, name)
    if not row:
        raise HTTPException(404, "Quelle nicht gefunden")
    values = {k: v for k, v in patch.model_dump(exclude_none=True).items()}
    if values:
        await session.execute(update(SourceState).where(SourceState.name == name).values(**values))
        await session.commit()
        await session.refresh(row)
    return row.to_dict()


@router.post("/collect", dependencies=[Depends(require_admin)])
async def collect_now(source: str | None = None) -> dict:
    """Sofort sammeln (ignoriert die Intervalle)."""
    force = [source] if source else list(engine.collectors.keys())
    unknown = [s for s in force if s not in engine.collectors]
    if unknown:
        raise HTTPException(400, f"Unbekannte Quelle: {', '.join(unknown)}")
    return await engine.tick(force=force)


# ---------------------------------------------------------- Suchbegriffe
@router.get("/terms")
async def list_terms(session: AsyncSession = Depends(get_session)) -> list[dict]:
    rows = (
        await session.execute(select(SearchTerm).order_by(desc(SearchTerm.hits), SearchTerm.term))
    ).scalars().all()
    return [r.to_dict() for r in rows]


@router.post("/terms", status_code=201, dependencies=[Depends(require_admin)])
async def create_term(body: TermIn, session: AsyncSession = Depends(get_session)) -> dict:
    exists = (
        await session.execute(
            select(SearchTerm).where(func.lower(SearchTerm.term) == body.term.lower())
        )
    ).scalar_one_or_none()
    if exists:
        raise HTTPException(409, f"Suchbegriff '{body.term}' existiert bereits")
    row = SearchTerm(
        term=body.term,
        category=body.category,
        platforms=body.platforms,
        enabled=body.enabled,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    await hub.broadcast("terms", {"action": "created", "term": row.to_dict()})
    return row.to_dict()


@router.patch("/terms/{term_id}", dependencies=[Depends(require_admin)])
async def patch_term(
    term_id: int, patch: TermPatch, session: AsyncSession = Depends(get_session)
) -> dict:
    row = await session.get(SearchTerm, term_id)
    if not row:
        raise HTTPException(404, "Suchbegriff nicht gefunden")
    values = patch.model_dump(exclude_none=True)
    if values:
        await session.execute(update(SearchTerm).where(SearchTerm.id == term_id).values(**values))
        await session.commit()
        await session.refresh(row)
    await hub.broadcast("terms", {"action": "updated", "term": row.to_dict()})
    return row.to_dict()


@router.delete(
    "/terms/{term_id}", status_code=204, response_class=Response,
    dependencies=[Depends(require_admin)],
)
async def delete_term(term_id: int, session: AsyncSession = Depends(get_session)):
    row = await session.get(SearchTerm, term_id)
    if not row:
        raise HTTPException(404, "Suchbegriff nicht gefunden")
    await session.execute(delete(SearchTerm).where(SearchTerm.id == term_id))
    await session.commit()
    await hub.broadcast("terms", {"action": "deleted", "id": term_id})


# -------------------------------------------------------------------- Log
@router.get("/log")
async def event_log(
    limit: int = Query(40, ge=1, le=300), session: AsyncSession = Depends(get_session)
) -> list[dict]:
    rows = (
        await session.execute(select(EventLog).order_by(desc(EventLog.ts)).limit(limit))
    ).scalars().all()
    return [r.to_dict() for r in rows]


@router.post("/maintenance/cleanup", dependencies=[Depends(require_admin)])
async def cleanup() -> dict:
    removed = await engine.cleanup()
    return {"removed": removed, "retention_days": settings.retention_days}


# ------------------------------------------------------------ Darstellung
@router.get("/settings")
async def get_ui_settings(session: AsyncSession = Depends(get_session)) -> dict:
    rows = (await session.execute(select(UiSetting))).scalars().all()
    values = {**DEFAULT_UI_SETTINGS, **{r.key: r.value for r in rows}}
    return values


@router.put("/settings", dependencies=[Depends(require_admin)])
async def put_ui_settings(
    patch: SettingsPatch, session: AsyncSession = Depends(get_session)
) -> dict:
    for key, value in patch.values.items():
        existing = await session.get(UiSetting, key)
        if existing:
            existing.value = value
        else:
            session.add(UiSetting(key=key, value=value))
    await session.commit()
    rows = (await session.execute(select(UiSetting))).scalars().all()
    values = {**DEFAULT_UI_SETTINGS, **{r.key: r.value for r in rows}}
    await hub.broadcast("settings", values)
    return values


# ------------------------------------------------------------- Diagnose
# Aus den in diesem Projekt tatsächlich aufgetretenen Fehlern zusammen-
# gestellt: eine kuratierte Checkliste, die als Erstes geprüft wird,
# bevor man in Logs sucht.
KNOWN_ISSUES: list[dict] = [
    {
        "id": "docker-desktop-not-running",
        "title": "Docker Desktop läuft nicht",
        "symptom": "„unable to get image … dockerDesktopLinuxEngine“ oder "
        "„open //./pipe/dockerDesktopLinuxEngine: Das System kann die "
        "angegebene Datei nicht finden“",
        "fix": "Docker Desktop öffnen und warten, bis das Symbol unten "
        "links grün ist. Prüfen mit: docker version. Danach erneut "
        "docker compose up --build.",
    },
    {
        "id": "env-not-picked-up",
        "title": "Zugangsdaten in .env werden nicht erkannt",
        "symptom": "Quelle zeigt weiter „anonym“ / „öffentliche JSON-API“, "
        "obwohl Handle/Token eingetragen wurden",
        "fix": ".env muss im Projektstamm liegen - direkt neben "
        "docker-compose.yml, nicht im backend-Ordner. Nach jeder Änderung "
        "das Backend neu starten (docker compose up -d --build bzw. "
        "uvicorn neu starten).",
    },
    {
        "id": "html-in-feed",
        "title": "HTML-Reste oder Reddit-Signatur im Beitragstext",
        "symptom": "Text enthält <div>, <!-- SC_OFF -->, &#32; oder "
        "„submitted by /u/… to r/… [link] [comments]“",
        "fix": "Behoben seit der HTML-Bereinigung (strip_html) in allen "
        "Collectoren. Betrifft nur Beiträge, die vor dem Update gesammelt "
        "wurden - alte Datenbank leeren, falls noch sichtbar.",
    },
    {
        "id": "reddit-403",
        "title": "Reddit meldet HTTP 403 / 429",
        "symptom": "Quelle „reddit“ zeigt Fehler ProxyError oder "
        "HTTP 403 Forbidden, RSS-Fallback läuft aber",
        "fix": "Öffentliche JSON-API ist scharf rate-limitiert. Für mehr "
        "Durchsatz REDDIT_CLIENT_ID/SECRET setzen (script-App unter "
        "reddit.com/prefs/apps).",
    },
]


@router.get("/diagnostics")
async def diagnostics(session: AsyncSession = Depends(get_session)) -> dict:
    # Datenbank wirklich anfragen, nicht nur Config lesen
    db_ok, db_detail = True, settings.database_url.split("://", 1)[0]
    try:
        await session.execute(text("SELECT 1"))
    except Exception as exc:
        db_ok, db_detail = False, str(exc)[:200]

    credentials = {
        "bluesky": {
            "configured": bool(settings.bluesky_handle and settings.bluesky_app_password),
            "handle": settings.bluesky_handle or None,
            "app_password": _mask(settings.bluesky_app_password),
        },
        "reddit": {
            "configured": bool(settings.reddit_client_id and settings.reddit_client_secret),
            "client_id": _mask(settings.reddit_client_id),
        },
        "x": {
            "configured": bool(settings.x_bearer_token or settings.nitter_list),
            "mode": "api" if settings.x_bearer_token else ("nitter" if settings.nitter_list else "keine"),
            "bearer_token": _mask(settings.x_bearer_token),
        },
        "facebook": {
            "configured": bool(
                (settings.facebook_page_token and settings.facebook_page_list)
                or settings.rssbridge_url
            ),
            "mode": "graph" if settings.facebook_page_token else ("rss-bridge" if settings.rssbridge_url else "keine"),
        },
    }

    return {
        "database": {"ok": db_ok, "engine": db_detail},
        "redis": {"connected": dedup.backend == "redis", "backend": dedup.backend},
        "websocket_clients": hub.count,
        "credentials": credentials,
        "known_issues": KNOWN_ISSUES,
    }

"""Bluesky / AT Protocol.

Zwei Modi:
  1. anonym  -> https://public.api.bsky.app  (kein Login, striktere Limits)
  2. auth    -> Session über App-Passwort auf bsky.social (stabiler)

Endpoint: app.bsky.feed.searchPosts  (sort=latest)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from dateutil import parser as dtparse

from ..config import settings
from .base import BaseCollector, CollectorError, RawItem

log = logging.getLogger("netzwache.collector.bluesky")


class BlueskyCollector(BaseCollector):
    name = "bluesky"
    platform = "bluesky"
    label = "Bluesky (AT Protocol)"
    default_interval = settings.interval_bluesky
    setup_hint = (
        "Läuft ohne Login. Für stabilere Rate-Limits BLUESKY_HANDLE und "
        "BLUESKY_APP_PASSWORD in der .env setzen (App-Passwort in den "
        "Bluesky-Einstellungen erzeugen, nicht das Hauptpasswort!)."
    )

    def __init__(self, client) -> None:
        super().__init__(client)
        self._jwt: str | None = None
        self._jwt_at: datetime | None = None
        self._session_fail_at: datetime | None = None

    def available(self) -> tuple[bool, str]:
        if settings.bluesky_handle and settings.bluesky_app_password:
            return True, "authentifiziert (App-Passwort)"
        return True, "anonym (public AppView)"

    # ------------------------------------------------------------------
    async def _ensure_session(self) -> str | None:
        """Holt/erneuert ein AT-Protocol Access-JWT, falls Credentials da sind.

        Gibt None zurück (anonymer Fallback), wenn keine Credentials gesetzt
        sind ODER der letzte Login-Versuch kürzlich fehlgeschlagen ist - sonst
        würde ein anhaltendes Rate-Limit bei jedem einzelnen Suchbegriff im
        selben Lauf erneut den Login-Endpunkt treffen (siehe fetch()).
        """
        if not (settings.bluesky_handle and settings.bluesky_app_password):
            return None
        fresh = (
            self._jwt
            and self._jwt_at
            and (datetime.now(timezone.utc) - self._jwt_at).total_seconds() < 90 * 60
        )
        if fresh:
            return self._jwt
        if (
            self._session_fail_at
            and (datetime.now(timezone.utc) - self._session_fail_at).total_seconds() < 120
        ):
            return None
        try:
            resp = await self._post_with_backoff(
                f"{settings.bluesky_pds}/xrpc/com.atproto.server.createSession",
                json={
                    "identifier": settings.bluesky_handle,
                    "password": settings.bluesky_app_password,
                },
            )
        except CollectorError as exc:
            self._session_fail_at = datetime.now(timezone.utc)
            log.warning("Bluesky-Login fehlgeschlagen, nutze anonyme Suche als Fallback: %s", exc)
            return None
        data = resp.json()
        self._jwt = data.get("accessJwt")
        self._jwt_at = datetime.now(timezone.utc)
        self._session_fail_at = None
        log.info("Bluesky-Session erneuert für %s", settings.bluesky_handle)
        return self._jwt

    async def _search(self, term: str, limit: int) -> list[dict]:
        jwt = await self._ensure_session()
        params = {"q": term, "limit": limit, "sort": "latest"}
        if jwt:
            resp = await self._get_with_backoff(
                f"{settings.bluesky_pds}/xrpc/app.bsky.feed.searchPosts",
                params=params,
                headers={"Authorization": f"Bearer {jwt}"},
            )
        else:
            resp = await self._get_with_backoff(
                f"{settings.bluesky_public_api}/xrpc/app.bsky.feed.searchPosts",
                params=params,
            )
        return resp.json().get("posts", [])

    # ------------------------------------------------------------------
    async def fetch(self, terms: list[str]) -> list[RawItem]:
        if not terms:
            return []
        # Wie bei Reddit pro Lauf begrenzen - sonst multipliziert ein
        # anhaltendes Rate-Limit die Anfragen mit jedem weiteren Suchbegriff.
        terms = terms[:8]
        per_term = max(5, min(25, settings.max_items_per_run // max(1, len(terms)) + 5))
        items: list[RawItem] = []
        errors: list[str] = []

        for term in terms:
            try:
                posts = await self._search(term, per_term)
            except CollectorError as exc:
                errors.append(f"{term}: {exc}")
                continue
            for p in posts:
                items.append(self._to_item(p, term))

        if not items and errors:
            raise CollectorError("; ".join(errors[:3]))
        return items

    def _to_item(self, p: dict, term: str) -> RawItem:
        record = p.get("record", {}) or {}
        author = p.get("author", {}) or {}
        handle = author.get("handle", "")
        uri = p.get("uri", "")
        rkey = uri.rsplit("/", 1)[-1] if uri else ""
        created = record.get("createdAt") or p.get("indexedAt")
        try:
            created_at = dtparse.isoparse(created) if created else self._now()
        except Exception:
            created_at = self._now()
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)

        langs = record.get("langs") or []
        return RawItem(
            platform="bluesky",
            external_id=uri or f"bsky:{rkey}",
            text=record.get("text", ""),
            url=f"https://bsky.app/profile/{handle}/post/{rkey}" if handle and rkey else "",
            author=author.get("displayName") or handle,
            author_handle=handle,
            lang=(langs[0][:8] if langs else ""),
            source=f"@{handle}" if handle else "bluesky",
            created_at=created_at,
            engagement={
                "likes": p.get("likeCount", 0),
                "reposts": p.get("repostCount", 0),
                "replies": p.get("replyCount", 0),
                "quotes": p.get("quoteCount", 0),
            },
            raw={"cid": p.get("cid"), "term": term},
        )

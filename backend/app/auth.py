"""Admin-Login: eine einzelne, per Env-Variable gesetzte Admin-Identität.

Kein Mehrbenutzer-System, keine Passwort-Hashes in einer Tabelle - bewusst
einfach gehalten, weil es genau eine Rolle gibt (Admin) und das Passwort
ausschließlich aus der Server-Umgebung kommt, nie aus Git oder dem Frontend.
Die Session selbst liegt in einem signierten, HttpOnly-Cookie (Starlette
SessionMiddleware), das Backend hält keinen eigenen Session-Store.
"""
from __future__ import annotations

import secrets

from fastapi import HTTPException, Request

from .config import settings


def verify_admin_credentials(username: str, password: str) -> bool:
    """Zeitkonstanter Vergleich, damit die Antwortzeit kein Timing-Orakel ist."""
    if not settings.admin_password:
        return False
    user_ok = secrets.compare_digest(username, settings.admin_username)
    pass_ok = secrets.compare_digest(password, settings.admin_password)
    return user_ok and pass_ok


def is_admin(request: Request) -> bool:
    return bool(request.session.get("admin"))


def require_admin(request: Request) -> None:
    """FastAPI-Dependency: hängt an jeden schreibenden Endpunkt.

    Nur das Verstecken von Buttons im Frontend reicht nicht - das hier ist
    die tatsächliche serverseitige Durchsetzung. 401, nicht 403: es gibt
    keine granularen Rollen, nur "angemeldet" oder "nicht angemeldet".
    """
    if not is_admin(request):
        raise HTTPException(status_code=401, detail="Admin-Anmeldung erforderlich")

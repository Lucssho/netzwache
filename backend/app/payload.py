"""Absicherung für raw_payload (Datenformat v2, siehe README).

Jeder Collector liefert über RawItem.raw_payload das rohe, per-Post-Quell-
objekt (z.B. ein einzelnes Bluesky-Post-Dict, ein einzelnes Reddit-Listing-
Element). Bevor das in der DB landet, läuft es hier durch:

  1. Zugangsdaten-artige Schlüssel werden entfernt (Tokens/Passwörter stehen
     ohnehin nur in Request-Headern, nie in Response-Bodies - das hier ist
     ein zusätzliches Sicherheitsnetz, kein primärer Schutz).
  2. Einzelne, ungewöhnlich lange Strings werden gekürzt.
  3. Ist das Ergebnis immer noch größer als das konfigurierte Limit
     (settings.raw_payload_max_bytes), wird härter gekürzt und das Ergebnis
     klar als gekürzt markiert (_truncated: true) - nie stillschweigend.

Läuft zentral in scheduler.py::_store(), nicht in jedem Collector einzeln -
so gilt die Absicherung garantiert für jede Quelle, auch für künftige.
"""
from __future__ import annotations

import json
import re
from typing import Any

_CREDENTIAL_KEY_RE = re.compile(
    r"(token|secret|password|passwort|authorization|auth_|cookie|jwt|api[_-]?key)",
    re.IGNORECASE,
)


def _strip_credentials(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: _strip_credentials(v)
            for k, v in value.items()
            if not _CREDENTIAL_KEY_RE.search(str(k))
        }
    if isinstance(value, list):
        return [_strip_credentials(v) for v in value]
    return value


def _truncate_strings(value: Any, field_limit: int, list_limit: int = 50) -> Any:
    if isinstance(value, str):
        if len(value) > field_limit:
            return value[:field_limit] + "…[gekürzt]"
        return value
    if isinstance(value, dict):
        return {k: _truncate_strings(v, field_limit, list_limit) for k, v in value.items()}
    if isinstance(value, list):
        return [_truncate_strings(v, field_limit, list_limit) for v in value[:list_limit]]
    return value


def sanitize_raw_payload(payload: dict | None, max_bytes: int = 20_000) -> dict:
    """Entfernt Zugangsdaten-artige Felder und begrenzt die Gesamtgröße.

    Gibt bei leerem Input ein leeres Dict zurück (kein None) - vereinfacht
    die Weiterverarbeitung (immer ein dict, nie None-Checks nötig)."""
    if not payload:
        return {}

    cleaned = _strip_credentials(payload)
    cleaned = _truncate_strings(cleaned, field_limit=4000)
    encoded = json.dumps(cleaned, default=str, ensure_ascii=False)
    if len(encoded.encode("utf-8")) <= max_bytes:
        return cleaned

    # Immer noch zu groß (z.B. sehr viele Felder/tief verschachtelt) - härter
    # kürzen statt den JSON-String an einer beliebigen Stelle abzuschneiden
    # (das würde ungültiges JSON erzeugen).
    cleaned = _truncate_strings(cleaned, field_limit=300, list_limit=10)
    encoded = json.dumps(cleaned, default=str, ensure_ascii=False)
    if len(encoded.encode("utf-8")) > max_bytes:
        # Auch nach hartem Kürzen zu groß - lieber ehrlich fast leer melden
        # als weiter zu raten, wie viel noch passt.
        return {"_truncated": True, "_reason": "payload exceeded size limit even after reduction"}

    cleaned["_truncated"] = True
    return cleaned

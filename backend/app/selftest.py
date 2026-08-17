"""Selbsttest: prüft jeden Collector gegen die echten Endpunkte.

Aufruf (im backend-Ordner, venv aktiv):
    python -m app.selftest
    python -m app.selftest bluesky reddit

Braucht Internet, aber weder Datenbank noch Redis - ideal um vor dem
ersten `docker compose up` zu sehen, welche Quellen bei dir laufen.
"""
from __future__ import annotations

import asyncio
import sys

import httpx

from .collectors import COLLECTOR_CLASSES
from .config import settings
from .enrich import enrich

TEST_TERMS = ["ransomware", "linux", "bundestag"]

G, R, Y, B, DIM, RST = "\033[92m", "\033[91m", "\033[93m", "\033[94m", "\033[2m", "\033[0m"


async def run(selected: list[str]) -> int:
    print(f"\n{B}NETZWACHE Selbsttest{RST}  ({settings.app_name} {settings.version})")
    print(f"{DIM}Suchbegriffe: {', '.join(TEST_TERMS)}{RST}\n")
    failures = 0

    async with httpx.AsyncClient(
        follow_redirects=True,
        headers={"User-Agent": settings.user_agent},
        timeout=settings.http_timeout,
    ) as client:
        for cls in COLLECTOR_CLASSES:
            if selected and cls.name not in selected:
                continue
            col = cls(client)
            ok, mode = col.available()
            head = f"{cls.label:<28}"
            if not ok:
                print(f"{Y}[ INAKTIV ]{RST} {head} {mode}")
                print(f"{DIM}            -> {cls.setup_hint}{RST}\n")
                continue
            print(f"{DIM}[ .. ]{RST} {head} Modus: {mode}", end="\r")
            try:
                items = await col.fetch(TEST_TERMS)
            except Exception as exc:
                failures += 1
                print(f"{R}[ FEHLER  ]{RST} {head} {type(exc).__name__}: {exc}")
                print(f"{DIM}            -> {cls.setup_hint}{RST}\n")
                continue

            print(f"{G}[   OK    ]{RST} {head} {len(items)} Beiträge  {DIM}({mode}){RST}")
            for it in items[:2]:
                meta = enrich(it.text, it.title, it.category_hint, TEST_TERMS)
                text = (it.title or it.text).replace("\n", " ")[:88]
                cats = ",".join(meta["categories"][:2]) or "-"
                print(f"{DIM}            {it.source or it.platform} | {cats} | {text}{RST}")
            print()

    if failures:
        print(f"{R}{failures} Quelle(n) mit Fehlern.{RST} Details oben.\n")
    else:
        print(f"{G}Alle aktiven Quellen liefern Daten.{RST}\n")
    return 1 if failures else 0


def main() -> None:
    selected = [a.lower() for a in sys.argv[1:]]
    raise SystemExit(asyncio.run(run(selected)))


if __name__ == "__main__":
    main()

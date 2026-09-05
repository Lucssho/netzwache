# NETZWACHE

**Plattformübergreifendes Live-Lagebild aus Bluesky, Reddit, Google News, X, Facebook und kuratierten News-Feeds.**
Backend in Python (FastAPI), Frontend in TypeScript/Vite, alles per Docker Compose startklar.

```
 _   _ _____ _____ _______        __    _    ____ _   _ _____
| \ | | ____|_   _|__  /\ \      / /_ _| |  / ___| | | | ____|
|  \| |  _|   | |   / /  \ \ /\ / / _` | | | |   | |_| |  _|
| |\  | |___  | |  / /_   \ V  V / (_| | | | |___|  _  | |___
|_| \_|_____| |_| /____|   \_/\_/ \__,_|_|  \____|_| |_|_____|
```

---

## Was das Ding macht

* sammelt **alle 10 Sekunden** neue Beiträge (der Takt ist konfigurierbar)
* **sechs Quellen-Adapter**: Bluesky, Reddit, Google News, X/Twitter, Facebook, News-/Security-Feeds
* **dedupliziert** über Redis + Unique-Index (kein Beitrag doppelt, auch nicht bei Cross-Posts)
* **kategorisiert automatisch** in `cybersecurity`, `it`, `nachrichten`, `alltag`
* erkennt **CVE-Nummern** und berechnet einen **Severity-Score 0–100**
* schiebt alles per **WebSocket live ins Dashboard** – ohne Reload
* **Suchbegriffe im Frontend pflegbar** – ein neuer Begriff wird sofort gespeichert **und** ein
  Sammellauf über alle Quellen ausgelöst; das Dashboard zeigt live, wie viele Treffer dabei
  reinkamen
* jeder Beitrag zeigt **Plattform-Symbol, Autor, Zeit und Link zur Originalquelle**
* **Darstellung** (Schriftart, Schriftgröße, Dichte) manuell umschaltbar über den `Aa`-Knopf,
  wirkt sofort auf die ganze Oberfläche und wird im Backend gespeichert
* **Diagnose-Panel** (⚕-Knopf) mit Live-Status von Datenbank/Redis, welche Zugangsdaten erkannt
  wurden, und einer kuratierten Liste der Stolpersteine, die in diesem Projekt tatsächlich
  aufgetreten sind (Docker Desktop nicht gestartet, `.env` am falschen Ort, HTML-Reste im Feed)

---

## Optik

Ein schwebendes Fenster im macOS-Stil (Ampel oben links, abgerundete, leicht transluzente
Panels) in der ursprünglichen Linux-Terminal-Farbwelt (Terminal-Grün, Amber, Bernstein,
Schwarz-Rot-Gold-Akzent). Jede Plattform hat ein eigenes SVG-Symbol statt eines Text-Badges
(X, Bluesky-Schmetterling, Reddit, Facebook, News/RSS) – dieselben Symbole erscheinen in der
Quellenliste, im Feed, in den Filter-Reitern und im Lagebild.

Schriftart und -größe sind über den `Aa`-Knopf in der Werkzeugleiste frei wählbar
(JetBrains Mono, Fira Code, SF Mono, Menlo, Consolas, Inter, Systemschrift · 11–18px · drei
Dichtestufen). Die Wahl gilt sofort für die komplette Oberfläche und wird über
`PUT /api/settings` persistiert, damit sie nach einem Neuladen erhalten bleibt.

---

## Schnellstart mit Docker (empfohlen)

```bash
cp .env.example .env          # (Windows: copy .env.example .env)
docker compose up --build
```

Dann:

| Was          | URL                          |
|--------------|------------------------------|
| Dashboard    | http://localhost:8080        |
| API          | http://localhost:8000/api    |
| API-Doku     | http://localhost:8000/docs   |
| WebSocket    | ws://localhost:8000/ws       |

**Ohne eine einzige Zeile Konfiguration laufen bereits Bluesky, Reddit, Google News und alle News-Feeds.**
X und Facebook bleiben als „inaktiv" markiert, bis du Zugangsdaten hinterlegst (siehe unten).

Stoppen: `docker compose down` · Daten mit löschen: `docker compose down -v`

---

## Entwicklung in VS Code (ohne Docker)

**Terminal 1 – Backend:**

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux/macOS
pip install -r requirements.txt

# ohne Postgres/Redis: SQLite + In-Memory-Dedup
set DATABASE_URL=sqlite+aiosqlite:///./netzwache.db
uvicorn app.main:app --reload --port 8000
```

**Terminal 2 – Frontend:**

```bash
cd frontend
npm install
npm run dev                      # http://localhost:5173
```

Der Vite-Dev-Server leitet `/api` und `/ws` automatisch an das Backend auf Port 8000 weiter.

Empfohlene VS-Code-Erweiterungen liegen in `.vscode/extensions.json`,
Start-Konfigurationen in `.vscode/launch.json` (F5 startet das Backend im Debugger).

---

## Läuft bei mir was? – Selbsttest

Bevor du das ganze System startest, prüfe jede Quelle einzeln gegen die echten Endpunkte:

```bash
cd backend
python -m app.selftest              # alle Quellen
python -m app.selftest bluesky      # nur eine
```

Ausgabe pro Quelle: `OK` mit Beispielbeiträgen, `INAKTIV` mit Einrichtungshinweis oder `FEHLER` mit Ursache.

---

## Die sechs Quellen im Detail

| Quelle | Zugang | Status ohne Konfiguration |
|--------|--------|---------------------------|
| **Bluesky** | AT Protocol, `app.bsky.feed.searchPosts` | **läuft sofort** (anonyme öffentliche Suche) |
| **Reddit** | öffentliche JSON-API, optional OAuth, RSS-Fallback | **läuft sofort** |
| **News/Security** | 20 kuratierte RSS-Feeds (BSI CERT-Bund, heise, Golem, tagesschau, Krebs, CISA …) | **läuft sofort** |
| **Google News** | öffentliche RSS-Suche pro Suchbegriff, kein Key | **läuft sofort** |
| **X / Twitter** | API v2 (Bearer-Token) **oder** Nitter-Mirror | inaktiv – siehe unten |
| **Facebook** | Graph API (eigene Seiten) **oder** RSS-Bridge | inaktiv – siehe unten |

### Warum X und Facebook nicht einfach mitlaufen

Das ist keine Bequemlichkeit, sondern der Stand der Plattformen:

* **X** hat die kostenlose Lese-API abgeschafft. Beiträge lesen geht nur noch über einen
  kostenpflichtigen Plan (`X_BEARER_TOKEN`) oder über einen Nitter-Mirror
  (`NITTER_INSTANCES`) – Mirrors sind aber unzuverlässig und verschwinden regelmäßig.
  Werkzeuge wie `snscrape` oder `twint`, die man auf GitHub findet, funktionieren nicht mehr.
* **Facebook** blockiert öffentliches Scrapen technisch und untersagt es in den
  Nutzungsbedingungen. Legal geht die Graph API für **eigene** Seiten
  (`FACEBOOK_PAGE_TOKEN` + `FACEBOOK_PAGE_IDS`) oder eine selbstgehostete RSS-Bridge.

Beide Adapter sind vollständig implementiert und schalten sich automatisch scharf,
sobald die passende Variable in der `.env` steht. Bis dahin melden sie sauber
„nicht konfiguriert", statt die Sammelschleife mit Fehlern zu fluten.

---

## Bedienung des Dashboards

| Aktion | Wirkung |
|--------|---------|
| Klick auf eine Quelle links | löst sofort einen Sammellauf **nur für diese Quelle** aus |
| Rechtsklick auf eine Quelle | Quelle an-/abschalten |
| Suchbegriff eintippen + `+` | Begriff wird gespeichert **und sofort ein Lauf gestartet** |
| `●` / `○` am Begriff | Begriff vorübergehend deaktivieren |
| `×` am Begriff | Begriff löschen |
| Plattform-/Themen-Tabs | filtern den Feed (holt passende Historie nach) |
| `SEV ≥`-Regler | blendet Beiträge unterhalb der Severity aus |
| **Leertaste** | Live-Stream pausieren / weiterlaufen lassen |
| **`/`** | springt in die Volltextsuche |
| Klick auf gekürzten Text | klappt den vollen Beitrag auf |

---

## API

| Methode | Pfad | Zweck |
|---------|------|-------|
| `GET` | `/api/health` | Laufzeit, Ticks, Dedup-Backend, WS-Clients |
| `GET` | `/api/meta` | registrierte Collector + Einrichtungshinweise |
| `GET` | `/api/posts` | Beiträge; Filter: `platform`, `source`, `category`, `tag`, `cve`, `q`, `min_severity`, `since_minutes` |
| `GET` | `/api/stats` | Kennzahlen, Zeitreihe, Top-Keywords, CVE-Watch |
| `GET` | `/api/sources` | Status aller Quellen |
| `PATCH` | `/api/sources/{name}` | Quelle an/aus, Intervall ändern |
| `POST` | `/api/collect` | sofort sammeln (optional `?source=bluesky`) |
| `GET/POST/PATCH/DELETE` | `/api/terms` | Suchbegriffe verwalten |
| `GET` | `/api/log` | Ereignisprotokoll |
| `GET/PUT` | `/api/settings` | Darstellung (Schriftart, -größe, Dichte) lesen/speichern |
| `GET` | `/api/diagnostics` | DB-/Redis-Status, erkannte Zugangsdaten (maskiert), bekannte Stolpersteine |
| `WS` | `/ws` | Livestream: `snapshot`, `posts`, `sources`, `log`, `settings`, `tick` |

Interaktive Doku: http://localhost:8000/docs

---

## Eine neue Plattform anbinden

1. `backend/app/collectors/meine_quelle.py` anlegen und von `BaseCollector` erben:

```python
class MeineQuelle(BaseCollector):
    name = "meinequelle"
    platform = "meinequelle"
    label = "Meine Quelle"
    default_interval = 60
    setup_hint = "Was der Nutzer konfigurieren muss."

    def available(self) -> tuple[bool, str]:
        return True, "bereit"

    async def fetch(self, terms: list[str]) -> list[RawItem]:
        resp = await self._get("https://…", params={"q": terms[0]})
        return [RawItem(platform=self.platform, external_id=…, text=…) for x in resp.json()]
```

2. Klasse in `backend/app/collectors/__init__.py` in `COLLECTOR_CLASSES` eintragen.

Fertig – Scheduler, Statusanzeige, Filter-Tab und Dashboard ziehen den Rest automatisch aus der Registry.

---

## Tests

```bash
cd backend
pip install -r requirements.txt
python -m pytest            # 26 Tests: Anreicherung, alle Collector (gemockt), API-Flow, Dedup
```

Die Tests brauchen weder Netz noch Postgres noch Redis – SQLite und In-Memory-Dedup springen ein.

---

## Datenmodell: Kategorien, Tags & CVEs

`categories`, `matched_terms` und `cve_ids` liegen weiterhin als JSON-Spalten auf `posts`
(für die Feed-Anzeige ohne zusätzlichen Join), zusätzlich aber auch normalisiert:

* **`categories`** (feste 4 Werte: cybersecurity/it/nachrichten/alltag) + **`post_categories`**
  (m:n, `post_id` + `category_id`)
* **`post_tags`** (`post_id` + `tag`, z.B. `"linux"`) - der Suchbegriff, den ein Post
  getroffen hat
* **`post_cves`** (`post_id` + `cve`, z.B. `"CVE-2026-83548"`)

`GET /api/posts?category=cybersecurity`, `?tag=linux` und `?cve=CVE-2026-83548` filtern über
einen echten `JOIN`, nicht über eine JSON-Array-Suche - lassen sich beliebig mit
`platform`/`source` kombinieren, z.B. `?platform=reddit&tag=linux`. `/api/stats.by_category`
und `top_cves` sind entsprechend ein einfaches `GROUP BY` über die jeweilige Tabelle.
`keywords` bleibt bewusst nur JSON (offenes Vokabular, siehe `db_json.py`).

Bestehende Posts (vor dieser Umstellung gesammelt) einmalig nachtragen:

```bash
make migrate-normalize       # oder: docker exec netzwache-backend python -m app.migrate_normalize
```

Idempotent - kann gefahrlos mehrfach laufen, überspringt bereits migrierte Zeilen.

---

## Indizes & Volltextsuche

`source` und `severity` sind jetzt indiziert (`ix_posts_source`, `ix_posts_severity`) - beide
werden von `/api/posts` gefiltert, liefen vorher aber als vollständiger Tabellenscan.

`?q=` nutzt auf Postgres echte Volltextsuche statt `LIKE '%...%'`: eine generierte
`search_vector`-Spalte (`tsvector` über `title`+`text`, deutsche Sprachkonfiguration) mit
GIN-Index, abgefragt über `websearch_to_tsquery` (versteht `"Wortgruppen"` und `-ausschluss`).
Die Spalte pflegt sich selbst - kein Anwendungscode schreibt sie. SQLite (Dev/Tests) hat keine
Entsprechung und bleibt beim bisherigen `LIKE`-Fallback (siehe `db_json.py`).

Sowohl die Indizes als auch die `search_vector`-Spalte werden beim Start automatisch angelegt
(`init_db()`, `CREATE INDEX IF NOT EXISTS` / `ADD COLUMN IF NOT EXISTS`) - kein separater
Migrationsschritt nötig, das läuft auch auf der schon existierenden `posts`-Tabelle nach.

---

## Speicherbegrenzung

Zwei automatische, voneinander unabhängige Räumungen laufen im Scheduler mit, keine davon
braucht einen manuellen Aufruf:

* **`MAX_POSTS`** (Standard 10000): harte Obergrenze für die `posts`-Tabelle. Nach jedem
  Sammel-Lauf, der neue Beiträge gespeichert hat, prüft der Scheduler die Gesamtzahl - wird die
  Grenze überschritten, fallen die ältesten Beiträge (nach `collected_at`) sofort raus, bis das
  Limit wieder eingehalten ist.
* **`RETENTION_DAYS`** (Standard 30) + **`CLEANUP_INTERVAL_SECONDS`** (Standard 86400 = 24h):
  zeitbasierte Räumung - alle X Sekunden werden Posts gelöscht, die älter als `RETENTION_DAYS`
  sind (nach `collected_at`), zusammen mit Log-Einträgen älter als 3 Tage. Läuft erstmals sofort
  beim Start des Backends, danach im konfigurierten Takt.

`POST /api/maintenance/cleanup` (Admin) stößt dieselbe zeitbasierte Räumung zusätzlich manuell an,
z.B. um nicht auf den nächsten automatischen Lauf zu warten.

---

## Backups

Ein eigener `backup`-Container (`docker-compose.yml`) sichert die Postgres-Datenbank automatisch:
ein Dump sofort beim Start des Stacks, danach alle 24h (`BACKUP_INTERVAL_SECONDS`). Von den
Dumps werden die **14 jüngsten** aufgehoben (`BACKUP_KEEP`) – bewusst mehr als einer, falls der
neueste Dump selbst schon aus einer beschädigten Datenbank gezogen wurde.

**Ablageort:** `./backups/netzwache-<UTC-Zeitstempel>.sql.gz` im Projektverzeichnis (Bind-Mount,
liegt also direkt auf dem Host, nicht nur im Docker-Volume). Der Ordner ist in `.gitignore`.

Sofortiger manueller Dump, zusätzlich zum täglichen Takt:

```bash
make backup                 # oder: docker exec netzwache-db pg_dump -U netzwache -d netzwache | gzip > backups/manual.sql.gz
```

**Wiederherstellen** (überschreibt die aktuelle Datenbank mit dem Stand aus dem Dump):

```bash
make restore FILE=backups/netzwache-20260902-030000.sql.gz
```

Das entspricht:

```bash
gunzip -c backups/netzwache-20260902-030000.sql.gz | docker exec -i netzwache-db psql -U netzwache -d netzwache
```

Läuft der Stack gerade nicht, zuerst `docker compose up -d db` (nur die Datenbank), dann restaurieren.

---

## Aufbau

```
netzwache/
├── docker-compose.yml          Postgres + Redis + Backend + Frontend
├── .env.example                alle Schalter, kommentiert
├── backend/
│   ├── app/
│   │   ├── main.py             FastAPI-App, Lifespan, WebSocket
│   │   ├── config.py           Einstellungen aus .env
│   │   ├── models.py           Post, Category, PostCategory, PostTag, PostCve, SearchTerm, SourceState, EventLog
│   │   ├── scheduler.py        10s-Takt, Rate-Limits, Speichern, Broadcast
│   │   ├── enrich.py           Kategorien, CVE, Severity, Keywords
│   │   ├── db_json.py          Dialektabhängige Suche in offenen JSON-Spalten (keywords, cve_ids)
│   │   ├── migrate_normalize.py  Einmalige Migration: post_categories/post_tags/post_cves aus Bestandsdaten befüllen
│   │   ├── dedup.py            Redis-Dedup mit Memory-Fallback
│   │   ├── hub.py              WebSocket-Broadcast
│   │   ├── selftest.py         Quellen einzeln gegen echte Endpunkte prüfen
│   │   ├── api/routes.py       REST-Endpunkte
│   │   └── collectors/         ein Modul je Plattform
│   └── tests/                  pytest
└── frontend/
    ├── src/
    │   ├── main.ts             Zustand, Ereignisse, Bootstrap
    │   ├── api.ts / ws.ts      REST-Client und Live-Stream
    │   ├── styles.css          Linux-Terminal-Optik
    │   └── components/         Header, Quellen, Begriffe, Feed, Lagebild, Log
    └── nginx.conf              Reverse-Proxy für den Produktions-Container
```

---

## Rechtliches

Gesammelt werden ausschließlich **öffentlich zugängliche** Inhalte über die dafür
vorgesehenen Schnittstellen. Es werden keine Logins umgangen und keine geschützten
Bereiche ausgelesen. Wer die Daten weiterverarbeitet, ist für die Einhaltung von
DSGVO und den Nutzungsbedingungen der jeweiligen Plattform selbst verantwortlich.
Die Rate-Limits pro Quelle sind bewusst konservativ voreingestellt – bitte nicht ohne
Grund herunterdrehen.

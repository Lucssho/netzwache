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
| `GET` | `/api/posts/{id}` | ein einzelner Beitrag - einzige Stelle, die zusätzlich `raw_payload` mitliefert (siehe [Datenformat v2](#datenformat-v2-neu-gesammelte-beiträge)) |
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

## Wo und wie die Daten gespeichert werden

**Speicherort:** Postgres 16 im Docker-Setup - ein eigener `db`-Container, dessen Daten im
benannten Docker-Volume `pgdata` liegen (`/var/lib/postgresql/data` im Container). Das
überlebt `docker compose down`, aber nicht `docker compose down -v` (siehe
[Schnellstart](#schnellstart-mit-docker-empfohlen)). Für die lokale Entwicklung ohne
Docker springt SQLite ein (eine einzelne Datei, `./netzwache.db`) - auch die Tests laufen
ausschließlich gegen SQLite, ganz ohne Netzwerk oder externe Dienste.

Redis (eigener `redis`-Container) speichert **keine** Beitragsinhalte - es hält nur eine
kurzlebige Menge bereits gesehener `content_hash`-Werte zur Deduplizierung vor
(`DEDUP_TTL_DAYS`, Standard 14 Tage). Fällt Redis aus, übernimmt ein In-Memory-Fallback
(siehe `dedup.py`) - weniger robust über einen Neustart hinweg, aber funktionsfähig.

**Was pro Beitrag gespeichert wird** - jeder gesammelte Beitrag landet als eine Zeile in
der `posts`-Tabelle:

| Spalte | Typ | Bedeutung |
|---|---|---|
| `id` | Integer, PK | interne, fortlaufende ID |
| `platform` | String | `bluesky` / `reddit` / `x` / `facebook` / `news` / `googlenews` |
| `source` | String | z.B. `"r/netsec"`, `"heise-security"`, `"@handle.bsky.social"` |
| `external_id` | String | ID des Beitrags auf der Original-Plattform |
| `content_hash` | String, unique | Hash über den Inhalt, für Deduplizierung |
| `author` / `author_handle` | String | Anzeigename / Handle des Autors |
| `title` / `text` | Text | Titel (falls vorhanden) und Volltext |
| `url` | Text | Link zum Original |
| `lang` | String | Sprachcode, falls von der Quelle geliefert |
| `created_at` | Timestamp | Original-Zeitpunkt laut Quelle |
| `collected_at` | Timestamp | Zeitpunkt, zu dem NETZWACHE den Beitrag eingesammelt hat |
| `categories` | JSON-Array | z.B. `["cybersecurity", "it"]` |
| `matched_terms` | JSON-Array | welche Suchbegriffe getroffen haben |
| `keywords` | JSON-Array | automatisch extrahierte Schlagwörter |
| `cve_ids` | JSON-Array | erkannte CVE-Nummern |
| `severity` | Integer 0-100 | berechneter Schweregrad |
| `engagement` | JSON | Likes/Reposts/Kommentare, falls von der Quelle geliefert |
| `raw` | JSON | **legacy**, klein: nur Lauf-Metadaten wie Modus/Suchbegriff/Feed-URL, **nicht** das vollständige Quellobjekt (siehe unten) |

> **Richtigstellung:** `raw` wurde früher als "unverändertes Rohobjekt der Quelle"
> beschrieben - das stimmte nie ganz. Tatsächlich schrieben die Collector dort nur ein
> kleines Metadaten-Dict hinein (z.B. `{"mode": "rss", "term": "linux"}`), nie das
> eigentliche Quellobjekt. Für neu gesammelte Beiträge (Version 2) übernimmt das neue
> Feld **`raw_payload`** diese Rolle ehrlich - siehe
> [Datenformat v2](#datenformat-v2-neu-gesammelte-beiträge) unten. `raw` bleibt aus
> Kompatibilitätsgründen unverändert bestehen.

Ein `UNIQUE`-Constraint auf (`platform`, `external_id`) plus ein eindeutiger Index auf
`content_hash` verhindern doppelte Zeilen, auch wenn derselbe Beitrag über zwei
Sammel-Läufe oder zwei Quellen hereinkommt.

**Weitere Tabellen:**

| Tabelle | Zweck |
|---|---|
| `search_terms` | vom Nutzer verwaltete Suchbegriffe (Text, Kategorie, aktiv/inaktiv, Trefferzähler) |
| `source_state` | Laufzeit-Status je Quelle (Status, letzter Lauf, Fehlerzähler) - füttert die Statusleiste |
| `ui_settings` | Key-Value-Speicher für Darstellung (Schriftart, -größe, Dichte, Theme) |
| `event_log` | kurzes Ereignisprotokoll fürs Dashboard |
| `categories`, `post_categories`, `post_tags`, `post_cves` | normalisierte m:n-Zuordnungen - siehe nächster Abschnitt |

Alle Tabellen und Indizes werden beim ersten Start automatisch angelegt (`init_db()` in
`db.py`) - für eine frische Installation ist kein separater Migrationsschritt nötig.

---

## Datenformat v2: neu gesammelte Beiträge

Ab dieser Version bekommen **neu gesammelte** Beiträge ein deutlich ehrlicheres, für
Auswertung/Forschung/KI-Weiterverarbeitung besser nutzbares Format. **Bestandsdaten
(rund 96.000 Beiträge zum Zeitpunkt dieser Änderung) wurden dabei bewusst nicht
angefasst** - kein Backfill, keine erneuten API-Aufrufe, keine Änderung an bestehenden
Zeilen. Das war eine harte Vorgabe für diese Erweiterung, kein Zufall.

### Version 1 vs. Version 2

Jeder Beitrag hat ein Feld **`data_version`**:

* **Version 1** - alles, was vor dieser Änderung gesammelt wurde. Erkennbar auch daran,
  dass `content_status` in der Datenbank `NULL` ist (die API gibt dafür `"legacy"`
  aus, siehe unten) und alle unten aufgeführten neuen Felder `NULL`/leer sind.
* **Version 2** - alles, was seit dieser Änderung neu gesammelt wird. `scheduler.py`
  setzt `data_version=2` ausschließlich für Beiträge, die tatsächlich frisch über
  einen Collector hereinkommen (`Engine._store()`) - nirgendwo sonst im Code wird
  Version 2 vergeben.

Ein fehlender oder `NULL`-Versionswert gilt als Version 1. Die API macht daraus explizit
`"data_version": 1` und `"content_status": "legacy"`, statt rohes `NULL` auszugeben
(siehe `Post.to_dict()` in `models.py`).

### Die neuen Felder

| Feld | Typ | Bedeutung |
|---|---|---|
| `data_version` | Integer | `1` (Bestandsdaten) oder `2` (neu gesammelt) |
| `content_type` | String/`null` | grobe Art: `post`, `self_post`/`link_post` (Reddit), `article` (RSS/News/Google News) |
| `content_status` | String | siehe [Die vier content_status-Werte](#die-vier-content_status-werte) unten |
| `summary` | Text/`null` | eigenständige Kurzfassung, **nur** wenn sie sich von `text` unterscheidet - sonst leer, um keinen Text doppelt zu speichern |
| `content_full` | Text/`null` | vollständiger Beitragstext, **nur** wenn `content_status = full` - sonst leer (kein Duplikat von `text`, wenn ohnehin nichts Vollständigeres vorliegt) |
| `canonical_url` | Text/`null` | aufgelöste Original-URL, nur wenn ohne zusätzlichen Netzwerk-Request möglich (siehe Plattform-Details unten) |
| `collector_mode` | String/`null` | z.B. `oauth`/`public`/`rss` (Reddit), `api`/`nitter` (X), `graph`/`rss_bridge` (Facebook), `public`/`authenticated` (Bluesky) |
| `engagement_collected_at` | Timestamp/`null` | Zeitpunkt der Engagement-**Momentaufnahme** (siehe unten) - `null`, wenn keine Engagement-Daten vorlagen |
| `media` | JSON-Array/`null` | `[{"type": "image"/"video"/"external_link"/"quoted_post", "url": "..."}]` - **nur URLs/Metadaten, nie Binärdaten** |
| `raw_payload` | JSON/`null` | sanitisiertes Rohobjekt **dieses einen** Beitrags (nicht die ganze Mehr-Posts-API-Antwort) - siehe [Raw-Payload-Absicherung](#raw-payload-absicherung) unten |

`text`, `title`, `url` und alle anderen bisherigen Felder bleiben unverändert bestehen
und werden von allen Collectoren weiterhin genauso befüllt wie vorher - bestehende
API-Konsumenten und das aktuelle Frontend funktionieren unverändert weiter.

### Die vier content_status-Werte

`content_status` beschreibt **den tatsächlich gespeicherten Inhalt**, nicht das, was
der Collector sich erhofft hat:

* **`full`** - der komplette verfügbare Beitragstext liegt vor (z.B. ein Bluesky-Post,
  ein Reddit-Selbstbeitrag mit vollständigem `selftext`). Das bloße Erreichen des
  plattformeigenen Zeichenlimits (Bluesky, X) gilt **nicht** automatisch als
  abgeschnitten.
* **`summary`** - nur eine Kurzfassung liegt vor (typisch für RSS-Feeds mit
  `<description>`).
* **`title_only`** - nur Titel (und ggf. Quelle) liegen vor - typisch für Google News
  und Reddit-Link-Posts (das externe Linkziel wird nicht nachgeladen).
* **`unavailable`** - kein brauchbarer Textinhalt vorhanden.
* **`legacy`** - kein echter Wert, sondern der API-Fallback für Bestandsdaten
  (Version 1) ohne `content_status`.

### Plattform-spezifische Einschränkungen

* **Bluesky** - immer `full`: die API liefert grundsätzlich den kompletten Post-Text.
  `collector_mode` zeigt `public` (anonyme Suche) oder `authenticated` (mit
  `BLUESKY_HANDLE`/`BLUESKY_APP_PASSWORD`). `media` deckt Bilder, externe Link-Karten
  und zitierte Posts ab (nur URLs).
* **Reddit** - `self_post` (eigener Text, `is_self=true`) vs. `link_post`
  (`is_self=false`) werden klar unterschieden. Bei Selbstbeiträgen mit Text: `full`.
  Bei Link-Posts: **immer `title_only`** - wir laden das externe Linkziel nicht nach,
  auch wenn es sich um einen Artikel handelt. Die externe Ziel-URL steht getrennt in
  `canonical_url`, der Reddit-eigene Permalink bleibt weiterhin in `url`.
  `collector_mode` zeigt `oauth`, `public` oder `rss` (RSS-Rückfall bei blockierter
  JSON-API - dort ist mangels Score/Flair/`is_self` `summary`/`title_only` der bestmögliche
  ehrliche Wert). **Reddit-Kommentare werden nicht gesammelt** - weder in Version 1
  noch in Version 2.
* **RSS/kuratierte News-Feeds** - `content_status` ist `summary`, wenn der Feed eine
  eigene `<description>` liefert, sonst `title_only`. **Es wird keine Publisher-Website
  automatisch abgegrast** - `content_full` bleibt entsprechend leer. `canonical_url`
  wird nur gefüllt, wenn der Feed selbst schon eine Original-URL mitliefert (z.B.
  FeedBurners `origLink` bei "The Hacker News") - das kostet keinen zusätzlichen
  Request.
* **Google News** - liefert fast immer nur Titel, Quelle, eine Weiterleitungs-URL und
  manchmal eine kurze Beschreibung. `content_status` entsprechend `title_only` oder
  `summary`. Die Google-Weiterleitung wird **nicht** aufgelöst (das läuft bei Google
  News per JavaScript, nicht per einfachem HTTP-Redirect - eine zuverlässige Auflösung
  bräuchte zusätzliche, aggressivere Requests) - `canonical_url` bleibt deshalb leer,
  statt eine vermutete URL zu behaupten.
* **X/Twitter und Facebook** - das bisherige "inaktiv ohne Zugangsdaten"-Verhalten bleibt
  unverändert. Liefert die offizielle API (X Bearer-Token, Facebook Graph API) einen
  Beitrag, ist `content_status = full` (kompletter Text). Der Facebook-RSS-Bridge-Modus
  und der Nitter-Fallback für X liefern bestenfalls eine Zusammenfassung
  (`collector_mode = rss_bridge` bzw. `nitter`).

### Engagement als Momentaufnahme

Engagement-Werte (Likes, Reposts, Kommentare, Shares, …) sind **eine Momentaufnahme
zum Sammelzeitpunkt**, keine fortlaufend aktualisierte Zählung. `engagement_collected_at`
hält fest, wann diese Momentaufnahme gemacht wurde - `null`, wenn eine Quelle für diesen
Beitrag gar keine Engagement-Daten geliefert hat.

Wichtig: **fehlende Werte werden nicht zu `0`**. Liefert eine Quelle einen Zähler gar
nicht (z.B. lässt Facebooks Graph API das `shares`-Objekt bei manchen Beiträgen komplett
weg), fehlt der entsprechende Schlüssel im `engagement`-JSON ganz - er wird nicht mit `0`
vorgetäuscht. Ein tatsächlicher Nullwert (die Quelle liefert explizit `0`) bleibt davon
unberührt und wird ganz normal als `0` gespeichert.

Eine fortlaufende Nachverfolgung von Engagement über die Zeit (z.B. "wie oft wurde dieser
Post seit dem Sammeln noch geliked") ist **nicht** Teil dieser Änderung. Dafür könnte
später ein eigenes, gezieltes Skript einzelne Beiträge erneut abfragen (siehe
[Gezielte Nachanreicherung](#gezielte-nachanreicherung-später) unten) - ohne die
komplette Tabelle zu scannen oder bestehende Zeilen automatisch zu verändern.

### Raw-Payload-Absicherung

`raw_payload` enthält das rohe Quellobjekt **dieses einen** Beitrags (z.B. ein einzelnes
Bluesky-Post-Dict, ein einzelnes Reddit-Listing-Element, ein einzelner Feed-Eintrag) -
nicht die komplette Mehr-Posts-API-Antwort. Bevor es gespeichert wird, läuft es zentral
durch `app/payload.py::sanitize_raw_payload()` (in `scheduler.py::_store()`, nicht in
jedem Collector einzeln - damit gilt der Schutz garantiert für jede Quelle):

1. **Zugangsdaten-artige Schlüssel werden entfernt** (alles, was nach Token, Passwort,
   Secret, Authorization, Cookie oder API-Key aussieht) - ein zusätzliches
   Sicherheitsnetz, da Tokens ohnehin nur in Request-Headern stehen, nie in den
   Antwort-Objekten selbst.
2. **Größenbegrenzung**: `RAW_PAYLOAD_MAX_BYTES` (Standard 20.000 Bytes/Post,
   konfigurierbar über `.env`). Einzelne, ungewöhnlich lange Textfelder werden zuerst
   gekürzt; reicht das nicht, wird härter gekürzt. Musste gekürzt werden, steht
   `"_truncated": true` im gespeicherten Objekt - nie stillschweigend.
3. **Keine Binärdaten** - Bilder/Videos werden nie heruntergeladen oder eingebettet,
   nur URLs und Metadaten (siehe `media`-Feld oben).

`raw_payload` steht **nicht** in der Liste `GET /api/posts` (das würde die Antwort bei
bis zu 500 Beiträgen unnötig aufblähen), sondern nur im Einzel-Post-Endpunkt
`GET /api/posts/{id}` - siehe [API](#api).

### Auswirkung auf den Speicherbedarf

Die neuen Felder sind bei Version-1-Zeilen alle `NULL` und kosten dort praktisch nichts
zusätzlich. Bei neu gesammelten (Version-2-)Zeilen kommt vor allem `raw_payload` dazu -
bis zu `RAW_PAYLOAD_MAX_BYTES` (Standard 20 KB) pro Beitrag zusätzlich, meist deutlich
weniger. Das bestehende Größenlimit (`MAX_POSTS_SIZE_GB`, siehe
[Speicherbegrenzung](#speicherbegrenzung)) berücksichtigt die tatsächliche Tabellengröße
und greift unverändert, unabhängig davon, wodurch eine Zeile groß geworden ist.

### Gezielte Nachanreicherung (später)

Diese Änderung bewusst **nicht** enthalten: ein Skript, das Bestandsdaten nachträglich
auf Version 2 anhebt. Falls das später gewünscht ist, wäre der sichere Ansatz ein
eigenständiges, manuell gestartetes Skript, das:

* gezielt einzelne, ausgewählte Beiträge verarbeitet (z.B. per ID-Liste oder Filter),
  statt die gesamte Tabelle zu scannen;
* dieselbe `sanitize_raw_payload()`-Logik wiederverwendet;
* `data_version` für diese Zeilen explizit auf `2` setzt, nachdem echte Daten
  nachgetragen wurden - nie pauschal für den ganzen Bestand.

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

Drei automatische, voneinander unabhängige Räumungen laufen im Scheduler mit, keine davon
braucht einen manuellen Aufruf:

* **`MAX_POSTS_SIZE_GB`** (Standard 15, nur **Postgres/Produktion**): harte Größenobergrenze für
  die `posts`-Tabelle inkl. ihrer eigenen Indizes (`pg_total_relation_size`). Nach jedem
  Sammel-Lauf, der neue Beiträge gespeichert hat, prüft der Scheduler die tatsächliche Größe -
  wird das Limit überschritten, fällt ein Stück der ältesten Beiträge (nach `collected_at`) raus,
  ungefähr **`POSTS_TRIM_CHUNK_MB`** (Standard 100 MB) pro Lauf - nicht alles auf einen Schlag.
  Wird das Limit später stark gesenkt, holt das mehrere Sammel-Läufe in kleinen Schritten nach.
  Die Menge pro Räumung ist eine Schätzung (Gesamtgröße ÷ Zeilenzahl × zu löschende Zeilen), kein
  exakter Bytewert. **Wichtig:** `DELETE` gibt Plattenplatz nicht an das Betriebssystem zurück
  (kein automatisches `VACUUM FULL`, das die Tabelle exklusiv sperren würde) - er wird nur für
  künftige Einträge wiederverwendet. Die Datenbankdatei wächst dadurch bis zum Limit und bleibt
  danach etwa auf der einmal erreichten Größe stehen, auch wenn man das Limit später senkt.
* **`MAX_POSTS`** (Standard 10000, nur **SQLite/Dev-Tests**): einfache Zeilen-Obergrenze, weil
  SQLite kein `pg_total_relation_size` kennt und die Datenmengen dort ohnehin klein bleiben.
* **`RETENTION_DAYS`** (Standard 30) + **`CLEANUP_INTERVAL_SECONDS`** (Standard 86400 = 24h):
  zeitbasierte Räumung, unabhängig von den beiden oben - alle X Sekunden werden Posts gelöscht,
  die älter als `RETENTION_DAYS` sind (nach `collected_at`), zusammen mit Log-Einträgen älter als
  3 Tage. Läuft erstmals sofort beim Start des Backends, danach im konfigurierten Takt.

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

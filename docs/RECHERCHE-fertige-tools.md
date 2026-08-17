# Gibt es dafür schon ein fertiges Tool auf GitHub?

Kurzantwort: **Nein – nichts, das die vier Plattformen zusammen abdeckt und
gleichzeitig ein Live-Dashboard mitbringt.** Deshalb der Eigenbau. Hier die geprüften
Kandidaten und warum sie ausscheiden.

## Geprüfte Projekte

| Projekt | Was es kann | Warum es nicht reicht |
|---|---|---|
| [ScriptSmith/socialreaper](https://github.com/ScriptSmith/socialreaper) | Sammelbibliothek für Facebook, Twitter, Reddit, YouTube, Pinterest, Tumblr | Seit Jahren unmaintained; baut auf API-Endpunkten, die es so nicht mehr gibt. Kein Bluesky, kein Dashboard, keine Live-Sammlung. |
| [harismuneer/Ultimate-Social-Scrapers](https://github.com/harismuneer/Ultimate-Social-Scrapers) | Facebook/Instagram/Twitter-Scraper | HTML-Scraping gegen Login-Wände; verstößt gegen die ToS und bricht laufend. Kein Backend, keine Oberfläche. |
| [JustAnotherArchivist/snscrape](https://github.com/JustAnotherArchivist/snscrape) | war lange *der* Standard für Twitter ohne API | Für X seit den API-Umstellungen praktisch tot. Reine CLI-Bibliothek. |
| twint | Twitter-Scraper | Archiviert/eingestellt. |
| [Altimis/Scweet](https://github.com/Altimis/Scweet) | X-Scraping mit Account-Pooling und Proxys | Braucht echte X-Accounts, riskiert Sperren, deckt nur X ab. |
| [AAndyProgram/SCrawler](https://github.com/AAndyProgram/SCrawler) | Medien-Downloader für sehr viele Seiten inkl. Bluesky | Zielt auf **Medien**, nicht auf Textanalyse; Desktop-App in VB.NET, keine API. |
| [drowsy-coder/Social-Scraper](https://github.com/drowsy-coder/Social-Scraper) | Reddit + Twitter nach CSV/JSON | Einzelnes Skript mit Selenium, keine Dauerbeobachtung, kein Frontend. |
| [Mixpost](https://mixpost.app/) | Self-hosted Social-Media-Suite | Ist ein **Publishing**-Tool (Beiträge veröffentlichen), kein Listening-Tool. |

## Was es an brauchbaren Bausteinen gibt

Diese sind in NETZWACHE eingebaut bzw. als Modus vorgesehen:

* **AT Protocol / Bluesky** – `app.bsky.feed.searchPosts` ist offen dokumentiert und
  ohne Bezahlschranke nutzbar. Beste Datenquelle des Projekts.
* **Reddit** – offizielle JSON-/OAuth-API, dokumentiert und legal nutzbar.
* **feedparser** – für die kuratierten News- und Security-Feeds.
* **X API v2** – funktioniert, aber nur mit bezahltem Plan (deshalb als Slot gebaut).
* **Meta Graph API** – funktioniert für Seiten, die man selbst verwaltet.

## Fazit

Die sinnvolle Bauweise ist nicht „ein fertiges Tool suchen", sondern eine
**Adapter-Architektur**: eine gemeinsame Schnittstelle, dahinter je Plattform ein
kleiner, austauschbarer Collector. Wenn X morgen die Preise ändert oder ein
Nitter-Mirror stirbt, tauscht man eine Datei – nicht das System.

Genau das ist `backend/app/collectors/`.

---

**Quellen:**

- [socialreaper – GitHub](https://github.com/ScriptSmith/socialreaper)
- [Ultimate-Social-Scrapers – GitHub](https://github.com/harismuneer/Ultimate-Social-Scrapers)
- [snscrape – GitHub](https://github.com/JustAnotherArchivist/snscrape)
- [Scweet – GitHub](https://github.com/Altimis/Scweet)
- [SCrawler – GitHub](https://github.com/AAndyProgram/SCrawler)
- [Social-Scraper – GitHub](https://github.com/drowsy-coder/Social-Scraper)
- [Bluesky API-Doku: app.bsky.feed.getPosts / API-Directory](https://docs.bsky.app/docs/advanced-guides/api-directory)
- [AT Protocol – Wikipedia](https://en.wikipedia.org/wiki/AT_Protocol)
- [Mixpost – Open Source Social Media Management](https://mixpost.app/)

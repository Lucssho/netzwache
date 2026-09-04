"""End-to-End-Test der API gegen eine SQLite-Datenbank (ohne Netzzugriff)."""
import httpx
import pytest


@pytest.mark.asyncio
async def test_full_api_flow(app_client: httpx.AsyncClient, admin_client: httpx.AsyncClient):
    # admin_client meldet sich auf demselben Client-Objekt an (Cookie-Jar wird
    # geteilt) - alle folgenden Schreibzugriffe über app_client laufen also
    # bereits als Admin.
    # Health
    r = await app_client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"

    # Meta: alle sechs Collector registriert
    meta = (await app_client.get("/api/meta")).json()
    names = {c["name"] for c in meta["collectors"]}
    assert names == {"bluesky", "reddit", "googlenews", "x", "facebook", "news"}

    # Quellen-Status wurde angelegt
    sources = (await app_client.get("/api/sources")).json()
    assert len(sources) == 6
    assert {s["name"] for s in sources} == names

    # Seed-Suchbegriffe vorhanden
    terms = (await app_client.get("/api/terms")).json()
    assert len(terms) >= 15

    # Neuen Suchbegriff anlegen
    r = await app_client.post("/api/terms", json={"term": "quantencomputer", "category": "it"})
    assert r.status_code == 201
    new_id = r.json()["id"]

    # Duplikat wird abgelehnt
    r = await app_client.post("/api/terms", json={"term": "Quantencomputer", "category": "it"})
    assert r.status_code == 409

    # Deaktivieren
    r = await app_client.patch(f"/api/terms/{new_id}", json={"enabled": False})
    assert r.json()["enabled"] is False

    # Löschen
    assert (await app_client.delete(f"/api/terms/{new_id}")).status_code == 204
    assert (await app_client.get(f"/api/posts/999999")).status_code == 404

    # Stats liefern vollständige Struktur
    stats = (await app_client.get("/api/stats")).json()
    for key in ("total", "by_platform", "by_category", "series", "top_keywords", "top_cves"):
        assert key in stats
    assert len(stats["series"]) == 30

    # Quelle konfigurieren
    r = await app_client.patch("/api/sources/news", json={"interval_seconds": 300})
    assert r.json()["interval_seconds"] == 300

    # Unbekannte Quelle -> 400
    assert (await app_client.post("/api/collect?source=tiktok")).status_code == 400


@pytest.mark.asyncio
async def test_posts_are_stored_deduplicated_and_filterable(app_client, seed_posts):
    await seed_posts()

    all_posts = (await app_client.get("/api/posts?limit=50")).json()
    assert all_posts["total"] == 3          # 4 eingespeist, 1 Duplikat verworfen

    only_bsky = (await app_client.get("/api/posts?platform=bluesky")).json()
    assert all(p["platform"] == "bluesky" for p in only_bsky["items"])
    assert len(only_bsky["items"]) == 1

    cyber = (await app_client.get("/api/posts?category=cybersecurity")).json()
    assert cyber["items"], "Cyber-Post sollte kategorisiert sein"
    assert all("cybersecurity" in p["categories"] for p in cyber["items"])

    high = (await app_client.get("/api/posts?min_severity=40")).json()
    assert all(p["severity"] >= 40 for p in high["items"])

    found = (await app_client.get("/api/posts?q=kernel")).json()
    assert len(found["items"]) == 1
    assert "kernel" in found["items"][0]["text"].lower()

    stats = (await app_client.get("/api/stats")).json()
    assert stats["total"] == 3
    assert stats["by_platform"]["bluesky"] == 1


@pytest.mark.asyncio
async def test_posts_source_filter_and_accurate_category_total(app_client, seed_posts):
    """source ist eine eigene Spalte (z.B. "r/linux"), unabhängig von
    platform. Und: total muss zum category-gefilterten Ergebnis passen -
    vorher ignorierte total den category-Filter komplett und zeigte die
    Zahl aus platform/q/min_severity/since_minutes an."""
    await seed_posts()

    # q= grenzt zusätzlich auf die Posts dieses Tests ein, damit die Zahlen
    # unabhängig von Daten aus anderen Tests in derselben (session-weiten) DB sind.
    only_linux_sub = (await app_client.get("/api/posts?source=r/linux&q=kernel")).json()
    assert only_linux_sub["total"] == 1
    assert only_linux_sub["items"][0]["source"] == "r/linux"

    no_match = (await app_client.get("/api/posts?source=r/does-not-exist&q=kernel")).json()
    assert no_match["total"] == 0
    assert no_match["items"] == []

    cyber = (await app_client.get("/api/posts?category=cybersecurity&q=ransomware")).json()
    assert cyber["total"] == len(cyber["items"]) == 1

    other_cat = (await app_client.get("/api/posts?category=it&q=ransomware")).json()
    assert other_cat["total"] == 0, "der Ransomware-Post ist nicht als 'it' kategorisiert"

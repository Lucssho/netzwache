"""Regressionstest: /api/stats muss über die GESAMTE posts-Tabelle
aggregieren (GROUP BY/COUNT in SQL), nicht nur über die letzten 600 Zeilen
wie zuvor. Mit einem eindeutigen Marker in >600 eigens eingefügten Posts
lässt sich das unabhängig von Daten aus anderen Tests nachweisen."""
from datetime import datetime, timezone

import pytest

from app.collectors.base import RawItem


@pytest.mark.asyncio
async def test_stats_aggregate_beyond_last_600_posts(app_client):
    from app.scheduler import engine

    marker = "zzzmarkerkeyword650"
    n = 650
    now = datetime.now(timezone.utc)
    items = [
        RawItem(
            platform="reddit",
            external_id=f"bulk-{i}",
            text=f"ransomware {marker} eintrag{i}",
            created_at=now,
        )
        for i in range(n)
    ]
    stored = await engine._store(items, [])
    assert len(stored) == n, "alle 650 Testposts müssen gespeichert werden (verschiedene external_id)"

    stats = (await app_client.get("/api/stats")).json()

    keyword_counts = dict(stats["top_keywords"])
    assert keyword_counts.get(marker, 0) >= n, (
        "top_keywords muss über die gesamte Tabelle zählen - vorher wurden nur "
        "die letzten 600 Posts betrachtet, hier sind es 650 mit demselben Keyword"
    )

    assert stats["by_category"]["cybersecurity"] >= n, (
        "by_category muss ebenfalls über die gesamte Tabelle aggregieren"
    )

"""Collector-Registry.

Eine neue Plattform anbinden:
  1. Datei in diesem Ordner anlegen, von BaseCollector erben
  2. Klasse hier in COLLECTOR_CLASSES eintragen
Der Scheduler, die Statusanzeige und das Frontend ziehen alles Weitere
automatisch aus der Registry.
"""
from __future__ import annotations

from .base import BaseCollector, CollectorError, RawItem
from .bluesky import BlueskyCollector
from .facebook import FacebookCollector
from .googlenews import GoogleNewsCollector
from .news import NewsCollector
from .reddit import RedditCollector
from .x_twitter import XCollector

COLLECTOR_CLASSES: list[type[BaseCollector]] = [
    BlueskyCollector,
    RedditCollector,
    XCollector,
    FacebookCollector,
    NewsCollector,
    GoogleNewsCollector,
]

__all__ = [
    "BaseCollector",
    "CollectorError",
    "RawItem",
    "COLLECTOR_CLASSES",
    "BlueskyCollector",
    "RedditCollector",
    "XCollector",
    "FacebookCollector",
    "NewsCollector",
    "GoogleNewsCollector",
]

"""Zentrale Konfiguration - alles über Umgebungsvariablen / .env steuerbar."""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"), env_file_encoding="utf-8", extra="ignore"
    )

    # --- Allgemein -----------------------------------------------------
    app_name: str = "NETZWACHE"
    version: str = "1.0.0"
    log_level: str = "INFO"
    cors_origins: str = "*"

    # --- Datenbank / Cache ---------------------------------------------
    # Postgres im Docker-Compose. Ohne Docker: sqlite+aiosqlite:///./netzwache.db
    database_url: str = "postgresql+asyncpg://netzwache:netzwache@db:5432/netzwache"
    redis_url: str = "redis://redis:6379/0"
    dedup_ttl_days: int = 14

    # --- Sammel-Takt ----------------------------------------------------
    tick_seconds: int = 10          # Haupt-Takt des Schedulers
    http_timeout: int = 20
    user_agent: str = "netzwache/1.0 (open-source OSINT dashboard; +https://localhost)"
    max_items_per_run: int = 50
    retention_days: int = 30        # Posts älter als X Tage werden aufgeräumt

    # --- Intervalle je Quelle (Sekunden, respektiert Rate-Limits) -------
    interval_bluesky: int = 300
    interval_reddit: int = 120
    interval_x: int = 60
    interval_facebook: int = 300
    interval_news: int = 120
    interval_googlenews: int = 60

    # --- Bluesky (AT Protocol) ------------------------------------------
    # Öffentliche Suche funktioniert meist ohne Login. Für stabile Limits:
    # App-Passwort unter bsky.app -> Settings -> App Passwords erzeugen.
    bluesky_handle: str = ""
    bluesky_app_password: str = ""
    bluesky_public_api: str = "https://public.api.bsky.app"
    bluesky_pds: str = "https://bsky.social"

    # --- Reddit ----------------------------------------------------------
    # Ohne Credentials wird die öffentliche JSON-API benutzt (striktere Limits).
    # Mit Credentials (https://www.reddit.com/prefs/apps -> "script"): OAuth.
    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    reddit_subreddits: str = "netsec,cybersecurity,linux,de_EDV,technology,programming,dachschaden,ich_iel,news"

    # --- X / Twitter ------------------------------------------------------
    # X hat keine brauchbare kostenlose Lese-API mehr. Der Adapter aktiviert
    # sich automatisch, sobald ein Bearer-Token oder Nitter-Mirror gesetzt ist.
    x_bearer_token: str = ""
    x_api_base: str = "https://api.x.com/2"
    nitter_instances: str = ""      # z.B. "https://nitter.privacydev.net,https://xcancel.com"

    # --- Facebook ---------------------------------------------------------
    # Graph API benötigt ein Page-Access-Token für Seiten, die du verwaltest.
    facebook_page_token: str = ""
    facebook_page_ids: str = ""     # kommagetrennt
    facebook_graph_base: str = "https://graph.facebook.com/v21.0"
    rssbridge_url: str = ""         # optionale selbstgehostete RSS-Bridge

    # --- News/RSS ---------------------------------------------------------
    news_keep_all: bool = True      # kuratierte Feeds auch ohne Term-Treffer behalten

    # --- Google News --------------------------------------------------------
    # Öffentliche RSS-Suche, kein Key nötig. Läuft pro aktivem Suchbegriff.

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def subreddit_list(self) -> list[str]:
        return [s.strip() for s in self.reddit_subreddits.split(",") if s.strip()]

    @property
    def nitter_list(self) -> list[str]:
        return [s.strip().rstrip("/") for s in self.nitter_instances.split(",") if s.strip()]

    @property
    def facebook_page_list(self) -> list[str]:
        return [s.strip() for s in self.facebook_page_ids.split(",") if s.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

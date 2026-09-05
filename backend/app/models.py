"""SQLAlchemy-Modelle. JSON statt JSONB, damit auch SQLite (Dev) läuft."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Post(Base):
    """Ein gesammelter Beitrag von irgendeiner Plattform."""

    __tablename__ = "posts"
    __table_args__ = (
        UniqueConstraint("platform", "external_id", name="uq_post_platform_external"),
        Index("ix_posts_collected_at", "collected_at"),
        Index("ix_posts_created_at", "created_at"),
        Index("ix_posts_platform", "platform"),
        Index("ix_posts_content_hash", "content_hash", unique=True),
        Index("ix_posts_source", "source"),
        Index("ix_posts_severity", "severity"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    platform: Mapped[str] = mapped_column(String(32))
    source: Mapped[str] = mapped_column(String(120), default="")   # z.B. "r/netsec", "heise-security"
    external_id: Mapped[str] = mapped_column(String(255))
    content_hash: Mapped[str] = mapped_column(String(64))

    author: Mapped[str] = mapped_column(String(255), default="")
    author_handle: Mapped[str] = mapped_column(String(255), default="")
    title: Mapped[str] = mapped_column(Text, default="")
    text: Mapped[str] = mapped_column(Text, default="")
    url: Mapped[str] = mapped_column(Text, default="")
    lang: Mapped[str] = mapped_column(String(8), default="")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    categories: Mapped[list] = mapped_column(JSON, default=list)
    matched_terms: Mapped[list] = mapped_column(JSON, default=list)
    keywords: Mapped[list] = mapped_column(JSON, default=list)
    cve_ids: Mapped[list] = mapped_column(JSON, default=list)
    severity: Mapped[int] = mapped_column(Integer, default=0)     # 0..100
    engagement: Mapped[dict] = mapped_column(JSON, default=dict)  # likes/reposts/comments
    raw: Mapped[dict] = mapped_column(JSON, default=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "platform": self.platform,
            "source": self.source,
            "external_id": self.external_id,
            "author": self.author,
            "author_handle": self.author_handle,
            "title": self.title,
            "text": self.text,
            "url": self.url,
            "lang": self.lang,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "collected_at": self.collected_at.isoformat() if self.collected_at else None,
            "categories": self.categories or [],
            "matched_terms": self.matched_terms or [],
            "keywords": self.keywords or [],
            "cve_ids": self.cve_ids or [],
            "severity": self.severity,
            "engagement": self.engagement or {},
        }


class Category(Base):
    """Feste Kategorien (cybersecurity/it/nachrichten/alltag) als echte
    Tabelle statt nur als String in der categories-JSON-Spalte auf Post."""

    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(32), unique=True)


class PostCategory(Base):
    """Normalisierte Post<->Kategorie-Zuordnung (m:n) - erlaubt ein
    echtes WHERE/JOIN über category_id statt einer JSON-Array-Suche.
    Die categories-JSON-Spalte auf Post bleibt zusätzlich bestehen, weil
    das Feed sie ohne einen weiteren Join direkt anzeigen kann."""

    __tablename__ = "post_categories"
    __table_args__ = (Index("ix_post_categories_category_id", "category_id"),)

    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id", ondelete="CASCADE"), primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"), primary_key=True)


class PostTag(Base):
    """Normalisierte Suchbegriff-Treffer eines Posts (das, was im Feed als
    „match: …" angezeigt wird) - ermöglicht WHERE tag = 'linux' statt einer
    JSON-Array-Suche über matched_terms. matched_terms auf Post bleibt
    zusätzlich für die Anzeige im Feed erhalten."""

    __tablename__ = "post_tags"
    __table_args__ = (Index("ix_post_tags_tag", "tag"),)

    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id", ondelete="CASCADE"), primary_key=True)
    tag: Mapped[str] = mapped_column(String(200), primary_key=True)


class PostCve(Base):
    """Normalisierte CVE-Treffer eines Posts - ermöglicht WHERE cve = 'CVE-...'
    statt einer JSON-Array-Suche über cve_ids, und ein echtes GROUP BY für
    top_cves. cve_ids auf Post bleibt zusätzlich für die Anzeige im Feed."""

    __tablename__ = "post_cves"
    __table_args__ = (Index("ix_post_cves_cve", "cve"),)

    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id", ondelete="CASCADE"), primary_key=True)
    cve: Mapped[str] = mapped_column(String(32), primary_key=True)


class SearchTerm(Base):
    """Vom Benutzer im Frontend verwaltete Suchbegriffe."""

    __tablename__ = "search_terms"
    __table_args__ = (UniqueConstraint("term", name="uq_term"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    term: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(32), default="it")
    platforms: Mapped[list] = mapped_column(JSON, default=list)   # [] = alle
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    hits: Mapped[int] = mapped_column(Integer, default=0)
    last_hit_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "term": self.term,
            "category": self.category,
            "platforms": self.platforms or [],
            "enabled": self.enabled,
            "hits": self.hits,
            "last_hit_at": self.last_hit_at.isoformat() if self.last_hit_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class SourceState(Base):
    """Laufzeit-Status je Collector - füttert die Statusleiste im Frontend."""

    __tablename__ = "source_state"

    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    platform: Mapped[str] = mapped_column(String(32), default="")
    label: Mapped[str] = mapped_column(String(120), default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(24), default="idle")  # idle|ok|error|disabled|degraded
    detail: Mapped[str] = mapped_column(Text, default="")
    interval_seconds: Mapped[int] = mapped_column(Integer, default=60)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_duration_ms: Mapped[float] = mapped_column(Float, default=0.0)
    items_last_run: Mapped[int] = mapped_column(Integer, default=0)
    items_total: Mapped[int] = mapped_column(Integer, default=0)
    errors_total: Mapped[int] = mapped_column(Integer, default=0)
    consecutive_errors: Mapped[int] = mapped_column(Integer, default=0)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "platform": self.platform,
            "label": self.label,
            "enabled": self.enabled,
            "status": self.status,
            "detail": self.detail,
            "interval_seconds": self.interval_seconds,
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
            "last_success_at": self.last_success_at.isoformat() if self.last_success_at else None,
            "last_duration_ms": round(self.last_duration_ms, 1),
            "items_last_run": self.items_last_run,
            "items_total": self.items_total,
            "errors_total": self.errors_total,
            "consecutive_errors": self.consecutive_errors,
        }


class UiSetting(Base):
    """Darstellungs-Einstellungen (Schriftart, Größe, Dichte, Theme).

    Einfache Key-Value-Tabelle, damit das Frontend die Optik über Geräte
    hinweg synchron hält, statt nur lokal im Browser zu speichern.
    """

    __tablename__ = "ui_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")


class EventLog(Base):
    """Kurzes Ereignis-Log für die Log-Zeile im Dashboard."""

    __tablename__ = "event_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    level: Mapped[str] = mapped_column(String(12), default="info")
    source: Mapped[str] = mapped_column(String(64), default="core")
    message: Mapped[str] = mapped_column(Text, default="")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "ts": self.ts.isoformat() if self.ts else None,
            "level": self.level,
            "source": self.source,
            "message": self.message,
        }

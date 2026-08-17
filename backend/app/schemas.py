"""Pydantic-Schemas für die REST-API."""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class TermIn(BaseModel):
    term: str = Field(min_length=2, max_length=200)
    category: str = "it"
    platforms: list[str] = []
    enabled: bool = True

    @field_validator("term")
    @classmethod
    def strip_term(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Suchbegriff darf nicht leer sein")
        return v

    @field_validator("category")
    @classmethod
    def valid_category(cls, v: str) -> str:
        allowed = {"cybersecurity", "it", "nachrichten", "alltag"}
        v = (v or "it").lower().strip()
        return v if v in allowed else "it"


class TermPatch(BaseModel):
    enabled: bool | None = None
    category: str | None = None
    platforms: list[str] | None = None


class SourcePatch(BaseModel):
    enabled: bool | None = None
    interval_seconds: int | None = Field(default=None, ge=5, le=3600)


class SettingsPatch(BaseModel):
    """Beliebige Darstellungs-Einstellungen als freies Key-Value-Set.

    Bewusst offen gehalten (kein festes Schema je Feld), damit das
    Frontend neue Optik-Optionen einführen kann, ohne das Backend
    anzufassen. Werte werden als String gespeichert.
    """

    values: dict[str, str] = Field(default_factory=dict, max_length=40)

    @field_validator("values")
    @classmethod
    def sane_keys(cls, v: dict[str, str]) -> dict[str, str]:
        for k in v:
            if not (1 <= len(k) <= 64) or not k.replace("_", "").replace("-", "").isalnum():
                raise ValueError(f"ungültiger Einstellungs-Schlüssel: {k!r}")
        return v

"""Anreicherung: Kategorien, Keywords, CVE-Erkennung, Severity-Score.

Bewusst regelbasiert und ohne ML-Modell: schnell, deterministisch,
nachvollziehbar - und ohne GPU/Modell-Download lauffähig.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from collections import Counter

CATEGORIES = ("cybersecurity", "it", "nachrichten", "alltag")

# Schlüsselwörter je Kategorie (deutsch + englisch)
CATEGORY_KEYWORDS: dict[str, set[str]] = {
    "cybersecurity": {
        "ransomware", "phishing", "malware", "botnet", "ddos", "exploit", "zero-day",
        "zeroday", "0day", "cve", "backdoor", "trojaner", "trojan", "spyware", "rootkit",
        "datenleck", "datenpanne", "data breach", "breach", "leak", "sicherheitslücke",
        "schwachstelle", "vulnerability", "patchday", "patch tuesday", "hardening",
        "bsi", "cert", "soc", "siem", "edr", "xdr", "pentest", "penetrationstest",
        "red team", "blue team", "threat intel", "apt", "supply chain attack",
        "verschlüsselung", "encryption", "ransom", "cyberangriff", "cyberattack",
        "hackerangriff", "credential", "passwort", "2fa", "mfa", "zero trust",
        "firewall", "ids", "ips", "cvss", "poc exploit", "rce", "privilege escalation",
        "sql injection", "xss", "csrf", "phisher", "infostealer", "keylogger",
        "dsgvo", "gdpr", "incident response", "forensik", "forensics", "opsec", "osint",
    },
    "it": {
        "linux", "kernel", "debian", "ubuntu", "arch linux", "fedora", "nixos",
        "open source", "opensource", "github", "gitlab", "git", "docker", "kubernetes",
        "k8s", "container", "devops", "ci/cd", "terraform", "ansible", "python",
        "typescript", "javascript", "rust", "golang", "java ", "c++", "php",
        "fastapi", "django", "react", "vue", "svelte", "vite", "node.js", "nodejs",
        "postgres", "postgresql", "mysql", "redis", "sqlite", "datenbank", "database",
        "api", "rest", "graphql", "websocket", "microservice", "serverless",
        "cloud", "aws", "azure", "gcp", "hetzner", "self-hosted", "selfhosted",
        "ki", "künstliche intelligenz", "artificial intelligence", "machine learning",
        "llm", "gpt", "claude", "neural", "compiler", "debugging", "refactoring",
        "software", "hardware", "gpu", "cpu", "raspberry pi", "server", "netzwerk",
        "programmierung", "programming", "entwickler", "developer", "framework",
        "shell", "bash", "systemd", "vim", "vs code", "terminal", "wayland", "gnome", "kde",
    },
    "nachrichten": {
        "bundestag", "bundesregierung", "kanzler", "regierung", "wahl", "wahlen",
        "koalition", "opposition", "minister", "ministerin", "parlament", "eu-kommission",
        "europäische union", "brüssel", "nato", "ukraine", "russland", "china", "usa",
        "krieg", "konflikt", "sanktionen", "diplomatie", "wirtschaft", "inflation",
        "konjunktur", "börse", "dax", "arbeitsmarkt", "streik", "tarif", "gericht",
        "urteil", "prozess", "staatsanwaltschaft", "polizei", "ermittlungen",
        "klimawandel", "energiewende", "gesetz", "verordnung", "reform", "haushalt",
        "breaking", "eilmeldung", "pressekonferenz", "studie", "umfrage",
    },
    "alltag": {
        "wetter", "unwetter", "hitze", "schnee", "regen", "sturm",
        "deutsche bahn", "db navigator", "verspätung", "streik bahn", "nahverkehr",
        "öpnv", "deutschlandticket", "stau", "autobahn", "tanken", "spritpreis",
        "supermarkt", "aldi", "lidl", "rewe", "edeka", "einkaufen", "preise",
        "miete", "wohnung", "wohnungsmarkt", "nebenkosten", "strompreis",
        "urlaub", "ferien", "wochenende", "feierabend", "kaffee", "rezept", "kochen",
        "fitness", "gesundheit", "arzt", "krankenkasse", "schule", "kita", "uni",
        "hochschule", "prüfung", "klausur", "bewerbung", "homeoffice", "montag",
        "alltag", "familie", "haustier", "hund", "katze", "fußball", "bundesliga",
    },
}

# Wörter, die den Severity-Score anheben (Cyber-Lagebild)
SEVERITY_WEIGHTS: dict[str, int] = {
    "zero-day": 30, "zeroday": 30, "0day": 30,
    "actively exploited": 35, "aktiv ausgenutzt": 35, "wird ausgenutzt": 30,
    "ransomware": 25, "wiper": 25, "kritische sicherheitslücke": 30,
    "critical": 20, "kritisch": 18, "notfall": 20, "emergency patch": 25,
    "rce": 25, "remote code execution": 25, "privilege escalation": 18,
    "datenleck": 20, "data breach": 20, "datenpanne": 18, "leaked": 12,
    "exploit": 15, "poc": 10, "malware": 12, "botnet": 12, "ddos": 10,
    "phishing": 8, "warnung": 10, "warnt": 8, "advisory": 8,
    "patch": 5, "update verfügbar": 5, "cvss": 10,
}

CVE_RE = re.compile(r"\bCVE-\d{4}-\d{4,7}\b", re.IGNORECASE)
URL_RE = re.compile(r"https?://\S+")
HASHTAG_RE = re.compile(r"#(\w{3,30})")
STOPWORDS = {
    "und", "oder", "aber", "der", "die", "das", "den", "dem", "des", "ein", "eine",
    "einen", "einem", "eines", "ist", "sind", "war", "waren", "wird", "werden",
    "nicht", "auch", "mit", "für", "von", "vom", "zum", "zur", "auf", "aus", "bei",
    "nach", "über", "unter", "durch", "gegen", "ohne", "wie", "was", "wer", "wann",
    "dass", "sich", "man", "mehr", "noch", "schon", "nur", "sehr", "kann", "haben",
    "hat", "the", "and", "for", "with", "that", "this", "you", "your", "are", "was",
    "have", "has", "from", "they", "them", "its", "but", "not", "all", "can", "will",
    "just", "about", "into", "out", "who", "why", "how", "new", "via", "der", "http",
    "https", "com", "www", "amp",
}


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    return re.sub(r"\s+", " ", text).strip()


def content_hash(platform: str, external_id: str, text: str) -> str:
    """Stabiler Hash: primär ID-basiert, Text als Rückfall gegen Cross-Posts."""
    base = f"{platform.lower()}::{external_id}" if external_id else f"text::{normalize(text).lower()}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def text_fingerprint(text: str) -> str:
    """Hash über den reinen Textinhalt - erkennt identische Cross-Posts."""
    cleaned = URL_RE.sub("", normalize(text)).lower()
    cleaned = re.sub(r"[^\w\s]", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return hashlib.sha256(cleaned.encode("utf-8")).hexdigest()


def detect_categories(text: str, hint: str = "") -> list[str]:
    """Ordnet einen Text den Kategorien zu (Mehrfachzuordnung möglich)."""
    low = normalize(text).lower()
    found: list[tuple[str, int]] = []
    for cat, words in CATEGORY_KEYWORDS.items():
        score = sum(1 for w in words if w in low)
        if score:
            found.append((cat, score))
    found.sort(key=lambda x: -x[1])
    cats = [c for c, _ in found]
    if hint and hint in CATEGORIES and hint not in cats:
        cats.insert(0, hint)
    return cats or (["alltag"] if not hint else [hint])


def extract_cves(text: str) -> list[str]:
    return sorted({m.upper() for m in CVE_RE.findall(text or "")})


def severity_score(text: str, cves: list[str]) -> int:
    low = normalize(text).lower()
    score = sum(w for k, w in SEVERITY_WEIGHTS.items() if k in low)
    if cves:
        score += 20 + 5 * min(len(cves), 4)
    return max(0, min(100, score))


def extract_keywords(text: str, limit: int = 8) -> list[str]:
    low = URL_RE.sub("", normalize(text)).lower()
    tags = [t.lower() for t in HASHTAG_RE.findall(low)]
    words = re.findall(r"[a-zäöüß][a-zäöüß0-9\-\.]{3,24}", low)
    words = [w.strip(".-") for w in words if w not in STOPWORDS and len(w) > 3]
    counts = Counter(tags * 2 + words)
    return [w for w, _ in counts.most_common(limit)]


def match_terms(text: str, terms: list[str]) -> list[str]:
    low = normalize(text).lower()
    return [t for t in terms if t.lower() in low]


def enrich(text: str, title: str = "", hint: str = "", terms: list[str] | None = None) -> dict:
    full = f"{title} {text}".strip()
    cves = extract_cves(full)
    return {
        "categories": detect_categories(full, hint),
        "cve_ids": cves,
        "severity": severity_score(full, cves),
        "keywords": extract_keywords(full),
        "matched_terms": match_terms(full, terms or []),
    }

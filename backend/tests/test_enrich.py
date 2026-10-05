"""Tests für die Anreicherung (Kategorien, CVE, Severity, Dedup-Hashes)."""
from app.enrich import (
    content_hash,
    detect_categories,
    enrich,
    extract_cves,
    extract_keywords,
    match_terms,
    severity_score,
    text_fingerprint,
)


def test_cve_extraction():
    text = "Kritische Lücke CVE-2026-12345 und cve-2025-0001 betroffen"
    assert extract_cves(text) == ["CVE-2025-0001", "CVE-2026-12345"]


def test_cve_none():
    assert extract_cves("keine luecke hier") == []


def test_categories_cyber():
    cats = detect_categories("Neue Ransomware verschlüsselt Server, BSI warnt vor Datenleck")
    assert cats[0] == "cybersecurity"


def test_categories_it():
    cats = detect_categories("Neues Linux-Kernel-Release mit Docker- und Kubernetes-Support")
    assert "it" in cats


def test_categories_alltag():
    cats = detect_categories("Deutsche Bahn: Verspätung beim Deutschlandticket, Strompreis steigt")
    assert "alltag" in cats


def test_categories_hint_wins():
    cats = detect_categories("irgendein text ohne signal", hint="nachrichten")
    assert cats[0] == "nachrichten"


def test_categories_fallback():
    assert detect_categories("xyz qrs tuv") == ["alltag"]


def test_weak_secondary_category_is_dropped():
    # Drucker/Server/Netzwerk/Software = 4x IT, nur "passwort" = 1x Cyber -> nur IT
    cats = detect_categories("Drucker per Netzwerk am Server einrichten: Software und Passwort setzen")
    assert cats == ["it"]


def test_strong_secondary_category_is_kept():
    # 2x IT (linux, docker) und 2x Cyber (ransomware, exploit) -> beide, kein Verwässern
    cats = detect_categories("Linux Docker Hosts: Ransomware nutzt Exploit")
    assert set(cats) == {"it", "cybersecurity"}


def test_dominant_cyber_beats_single_it_word():
    cats = detect_categories("Ransomware-Angriff: Phishing, Datenleck und Exploit auf einem Server")
    assert cats == ["cybersecurity"]


def test_category_keywords_need_word_boundaries():
    # "ki" darf nicht in "Kirche", "uni" nicht in "Union" und "rest" nicht in "interessant" anschlagen
    assert detect_categories("Die Kirche der Union ist interessant") == ["alltag"]


def test_severity_rises_with_cve():
    low = severity_score("normales update verfügbar", [])
    high = severity_score("zero-day wird aktiv ausgenutzt, ransomware", ["CVE-2026-1"])
    assert high > low
    assert 0 <= high <= 100


def test_severity_capped():
    text = "zero-day actively exploited ransomware critical rce datenleck exploit cvss"
    assert severity_score(text, ["CVE-2026-1", "CVE-2026-2"]) == 100


def test_match_terms_case_insensitive():
    assert match_terms("Großer RANSOMWARE-Angriff", ["ransomware", "linux"]) == ["ransomware"]


def test_keywords_skip_stopwords():
    kws = extract_keywords("das ist ein test mit kubernetes und kubernetes cluster")
    assert "kubernetes" in kws
    assert "ist" not in kws


def test_content_hash_stable_and_unique():
    a = content_hash("bluesky", "at://x/1", "hallo")
    b = content_hash("bluesky", "at://x/1", "anderer text")
    c = content_hash("reddit", "at://x/1", "hallo")
    assert a == b          # ID entscheidet
    assert a != c          # Plattform trennt


def test_text_fingerprint_ignores_urls_and_case():
    a = text_fingerprint("Hallo Welt https://example.com/x")
    b = text_fingerprint("hallo   welt   https://andere.de/y")
    assert a == b


def test_enrich_shape():
    out = enrich("Ransomware trifft Klinik, CVE-2026-9999", terms=["ransomware"])
    assert set(out) == {"categories", "cve_ids", "severity", "keywords", "matched_terms"}
    assert out["cve_ids"] == ["CVE-2026-9999"]
    assert out["matched_terms"] == ["ransomware"]
    assert out["categories"][0] == "cybersecurity"

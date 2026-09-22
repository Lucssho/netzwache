"""Die gemeinsame Trefferdefinition für Suchbegriffe (enrich.term_regex) und ihre Verwendung in API/Tagging.

Die Fälle stammen aus echten Daten: "BSI" traf früher "We-bsi-te" und "Ab-si-cherung"
(217 von 320 Tags falsch), während deutsche Formen wie "Sicherheitslücken" oder
"Strompreisbremse" im Fokus-Modus verloren gingen.
"""
from datetime import datetime, timezone

import pytest

from app.collectors.base import RawItem
from app.enrich import enrich, match_terms, pg_term_pattern, term_regex


def hit(term: str, text: str) -> bool:
    return bool(term_regex(term).search(text))


# ------------------------------------------------------------ Wortanfang
@pytest.mark.parametrize(
    "text",
    [
        "Show HN: A website that tracks food prices",
        "Die lebenslange Absicherung hat einen Zweck",
        "https://websafely.app/website/example.com",
        "and hit publish on my website",
    ],
)
def test_short_term_does_not_match_inside_words(text):
    assert not hit("BSI", text)


@pytest.mark.parametrize(
    "text",
    ["Das BSI warnt vor Angriffen", "BSI-Warnung zu Exchange", "bsi meldet", "Lagebericht (BSI)", "Die BSIs der Länder"],
)
def test_short_term_matches_as_word(text):
    assert hit("BSI", text)


def test_short_term_rejects_longer_words_starting_with_it():
    assert not hit("BSI", "Bsigmund und BSIX sind keine Treffer")


def test_cve_matches_ids_and_plural():
    assert hit("CVE", "Details zu CVE-2026-1234")
    assert hit("CVE", "mehrere CVEs betroffen")
    assert not hit("CVE", "Rezeptur ohne Bezug, aber Revecvex")


# ------------------------------------------------- deutsche Formen bleiben
@pytest.mark.parametrize(
    "term,text",
    [
        ("sicherheitslücke", "Linux-Kernel-Sicherheitslücken:"),
        ("sicherheitslücke", "Kritische Sicherheitslücke in Exchange"),
        ("strompreis", "Debatte um die Strompreisbremse"),
        ("cyberangriff", "Mehrere Cyberangriffe auf Kliniken"),
        ("bundestag", "Beschluss des Bundestages"),
        ("linux", "Linuxkernel 7.0 und Linux-Distributionen"),
        ("inflation", "Die Inflationsrate steigt"),
    ],
)
def test_long_term_allows_german_endings_and_compounds(term, text):
    assert hit(term, text)


def test_long_term_still_needs_a_word_start():
    # zusammengezogene Komposita mit dem Begriff am ENDE gelten bewusst nicht
    assert not hit("sicherheitslücke", "Kernelsicherheitslücke")
    assert not hit("linux", "Gnulinux")


# ----------------------------------------------------------- Trenner/Schreibung
@pytest.mark.parametrize("text", ["ein Zero-Day im Browser", "Zero Day Exploit", "Zeroday-Lücke", "ZERO-DAY"])
def test_hyphen_and_space_are_interchangeable(text):
    assert hit("zero-day", text)


def test_multiword_terms():
    assert hit("open source", "Open-Source-Projekt und Opensource")
    assert hit("eu kommission", "Die EU-Kommission plant")
    assert not hit("eu kommission", "EU und Kommission getrennt")
    assert hit("deutsche bahn", "Deutsche Bahn streikt")


def test_case_insensitive_including_umlauts():
    assert hit("sicherheitslücke", "SICHERHEITSLÜCKE gemeldet")
    assert hit("Sicherheitslücke", "sicherheitslücken")


def test_special_characters_are_literal_and_empty_never_matches():
    assert hit("c++", "Wir schreiben C++ Code")
    assert not hit("c++", "Wir schreiben Cpp Code")
    assert not hit("a.b", "axb")
    assert not hit("", "irgendwas")
    assert not hit("  - ", "irgendwas")
    assert match_terms("Text", [""]) == []


def test_pg_pattern_mirrors_the_python_definition():
    assert pg_term_pattern("BSI") == r"(?<![[:alnum:]_])BSI" + r"s?(?![[:alnum:]_])"
    assert pg_term_pattern("zero-day") == r"(?<![[:alnum:]_])zero[\s\-]*day"
    # Sonderzeichen werden maskiert; "c++" ist mit 3 Zeichen ein kurzer Begriff (Endgrenze)
    assert pg_term_pattern("c++") == r"(?<![[:alnum:]_])c\+\+" + r"s?(?![[:alnum:]_])"
    assert pg_term_pattern("linux") == r"(?<![[:alnum:]_])linux"  # lang: beliebige Endung erlaubt
    assert pg_term_pattern("  ") is None


# ------------------------------------------------------------ enrich(extra=)
def test_author_and_source_count_for_tags_only():
    out = enrich("Ein Beitrag ohne das Stichwort", "Titel", "", ["linux"], extra="alice r/linux")
    assert out["matched_terms"] == ["linux"], "Quelle r/linux zählt für Tags (wie Volltextsuche und Fokus-Modus)"
    plain = enrich("Ein Beitrag ohne das Stichwort", "Titel", "", ["linux"])
    assert plain["matched_terms"] == []
    # Kategorien/Keywords hängen weiter nur an Titel + Text
    assert "linux" not in out["keywords"]
    assert out["categories"] == plain["categories"]


# --------------------------------------------------------------------- API
def _raw(ext, text, source="", author="", title=""):
    return RawItem(
        platform="bluesky",
        external_id=ext,
        text=text,
        title=title,
        source=source,
        author=author,
        created_at=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_api_term_filter_uses_the_shared_definition(app_client):
    from app.scheduler import engine

    await engine._store(
        [
            _raw("tm-real", "Das BSI warnt vor einer neuen Lücke"),
            _raw("tm-website", "Bau dir eine eigene Website in einer Stunde"),
            _raw("tm-absich", "Absicherung von Servern leicht gemacht"),
            _raw("tm-plural", "Zwei kritische Sicherheitslücken im Kernel"),
            _raw("tm-source", "Neuer Release ist da", source="r/linux"),
            _raw("tm-none", "Völlig anderes Thema, Wetter und Sport"),
        ],
        [],
    )

    bsi = {p["external_id"] for p in (await app_client.get("/api/posts?limit=500&term=BSI")).json()["items"]}
    assert "tm-real" in bsi
    assert not {"tm-website", "tm-absich"} & bsi, "Teilstrings mitten im Wort dürfen nicht treffen"

    luecke = {p["external_id"] for p in (await app_client.get("/api/posts?limit=500&term=sicherheitslücke")).json()["items"]}
    assert "tm-plural" in luecke, "deutsche Pluralform muss treffen"

    linux = {p["external_id"] for p in (await app_client.get("/api/posts?limit=500&term=linux")).json()["items"]}
    assert "tm-source" in linux, "Treffer nur in der Quelle (r/linux) zählt"

    res = (await app_client.get("/api/posts?limit=1&term=nichtvorhandeneswortxyz")).json()
    assert res["total"] == 0 and res["items"] == []


@pytest.mark.asyncio
async def test_api_term_total_counts_everything_not_just_the_page(app_client):
    from app.scheduler import engine

    await engine._store([_raw(f"tm-page-{i}", f"Docker Beitrag Nummer {i} zum Testen der Seitenzahl") for i in range(7)], [])
    res = (await app_client.get("/api/posts?limit=3&term=docker")).json()
    assert len(res["items"]) == 3
    assert res["total"] >= 7, "total zählt alle Treffer, nicht nur die aktuelle Seite (Grundlage für den Fokus-Zähler)"
    page2 = (await app_client.get("/api/posts?limit=3&offset=3&term=docker")).json()
    assert {p["id"] for p in res["items"]}.isdisjoint({p["id"] for p in page2["items"]})


@pytest.mark.asyncio
async def test_api_tag_filter_is_case_insensitive(app_client):
    from app.scheduler import engine

    await engine._store([_raw("tm-tag", "Das BSI meldet etwas Neues zu Exchange")], ["BSI"])
    upper = (await app_client.get("/api/posts?limit=500&tag=BSI")).json()
    lower = (await app_client.get("/api/posts?limit=500&tag=bsi")).json()
    assert "tm-tag" in {p["external_id"] for p in upper["items"]}
    assert lower["total"] == upper["total"], "?tag=bsi darf nicht 0 liefern, wenn ?tag=BSI Treffer hat"


@pytest.mark.asyncio
async def test_new_posts_are_tagged_with_the_shared_definition(app_client):
    from app.scheduler import engine

    stored = await engine._store(
        [
            _raw("tm-tagged-1", "Kritische Sicherheitslücken bei Herstellern"),
            _raw("tm-tagged-2", "Meine neue Website ist online"),
            _raw("tm-tagged-3", "Release-Notes", source="r/selfhosted"),
        ],
        ["sicherheitslücke", "BSI", "selfhosted"],
    )
    tags = {p["external_id"]: set(p["matched_terms"]) for p in stored}
    assert tags["tm-tagged-1"] == {"sicherheitslücke"}
    assert tags["tm-tagged-2"] == set(), "'Website' darf nicht mehr mit BSI getaggt werden"
    assert tags["tm-tagged-3"] == {"selfhosted"}

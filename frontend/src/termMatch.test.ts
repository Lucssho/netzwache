import { describe, expect, it } from "vitest";

import { containsTerm, postHaystack, termRegex } from "./termMatch";

// Dieselben Fälle wie backend/tests/test_term_matching.py - die beiden
// Implementierungen müssen für dieselben Daten dieselbe Antwort geben.
describe("containsTerm - Wortanfang", () => {
  it.each([
    "Show HN: A website that tracks food prices",
    "Die lebenslange Absicherung hat einen Zweck",
    "https://websafely.app/website/example.com",
    "Bsigmund und BSIX sind keine Treffer",
  ])("kurzer Begriff trifft nicht mitten im Wort: %s", (text) => {
    expect(containsTerm(text, "BSI")).toBe(false);
  });

  it.each(["Das BSI warnt vor Angriffen", "BSI-Warnung zu Exchange", "bsi meldet", "Lagebericht (BSI)", "Die BSIs der Länder"])(
    "kurzer Begriff trifft als Wort: %s",
    (text) => {
      expect(containsTerm(text, "BSI")).toBe(true);
    },
  );

  it("CVE trifft IDs und Plural", () => {
    expect(containsTerm("Details zu CVE-2026-1234", "CVE")).toBe(true);
    expect(containsTerm("mehrere CVEs betroffen", "CVE")).toBe(true);
  });
});

describe("containsTerm - deutsche Formen bleiben", () => {
  it.each([
    ["sicherheitslücke", "Linux-Kernel-Sicherheitslücken:"],
    ["sicherheitslücke", "Kritische Sicherheitslücke in Exchange"],
    ["strompreis", "Debatte um die Strompreisbremse"],
    ["cyberangriff", "Mehrere Cyberangriffe auf Kliniken"],
    ["bundestag", "Beschluss des Bundestages"],
    ["linux", "Linuxkernel 7.0 und Linux-Distributionen"],
    ["inflation", "Die Inflationsrate steigt"],
  ])("%s trifft %s", (term, text) => {
    expect(containsTerm(text, term)).toBe(true);
  });

  it("lange Begriffe brauchen trotzdem einen Wortanfang", () => {
    expect(containsTerm("Kernelsicherheitslücke", "sicherheitslücke")).toBe(false);
    expect(containsTerm("Gnulinux", "linux")).toBe(false);
  });
});

describe("containsTerm - Trenner, Schreibung, Sonderzeichen", () => {
  it.each(["ein Zero-Day im Browser", "Zero Day Exploit", "Zeroday-Lücke", "ZERO-DAY"])("zero-day trifft %s", (text) => {
    expect(containsTerm(text, "zero-day")).toBe(true);
  });

  it("mehrteilige Begriffe", () => {
    expect(containsTerm("Open-Source-Projekt und Opensource", "open source")).toBe(true);
    expect(containsTerm("Die EU-Kommission plant", "eu kommission")).toBe(true);
    expect(containsTerm("EU und Kommission getrennt", "eu kommission")).toBe(false);
  });

  it("Groß-/Kleinschreibung inkl. Umlauten egal", () => {
    expect(containsTerm("SICHERHEITSLÜCKE gemeldet", "sicherheitslücke")).toBe(true);
    expect(containsTerm("sicherheitslücken", "Sicherheitslücke")).toBe(true);
  });

  it("Sonderzeichen sind wörtlich, leerer Begriff trifft nie", () => {
    expect(containsTerm("Wir schreiben C++ Code", "c++")).toBe(true);
    expect(containsTerm("Wir schreiben Cpp Code", "c++")).toBe(false);
    expect(containsTerm("axb", "a.b")).toBe(false);
    expect(termRegex("")).toBeNull();
    expect(containsTerm("irgendwas", "  - ")).toBe(false);
  });
});

describe("postHaystack", () => {
  it("umfasst Titel, Text, Autor und Quelle (Quelle r/linux zählt für 'linux')", () => {
    const p = { title: "Release", text: "Neue Version", author: "alice", source: "r/linux" };
    expect(containsTerm(postHaystack(p), "linux")).toBe(true);
    expect(postHaystack({ title: null, text: undefined })).toBe("   ");
  });
});

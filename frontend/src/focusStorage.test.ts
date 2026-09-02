import { afterEach, describe, expect, it, vi } from "vitest";
import { getFocusTerm, getFocusWindowMinutes, setFocusTerm, setFocusWindowMinutes } from "./focusStorage";

/** Einfache In-Memory-Storage, damit sich zwei "Sitzungen" (Tabs) unabhängig
 * voneinander simulieren lassen - echtes sessionStorage ist pro Tab isoliert,
 * das lässt sich innerhalb eines einzelnen jsdom-Fensters nicht direkt
 * abbilden, wohl aber durch zwei getrennte Storage-Objekte. */
function fakeSessionStorage(): Storage {
  const data = new Map<string, string>();
  return {
    getItem: (k: string) => data.get(k) ?? null,
    setItem: (k: string, v: string) => void data.set(k, v),
    removeItem: (k: string) => void data.delete(k),
    clear: () => data.clear(),
    key: (i: number) => Array.from(data.keys())[i] ?? null,
    get length() {
      return data.size;
    },
  } as Storage;
}

afterEach(() => {
  vi.unstubAllGlobals();
  sessionStorage.clear();
});

describe("Fokus-Modus-Speicherung (sessionStorage)", () => {
  it("speichert und liest die Auswahl zurück", () => {
    setFocusTerm("ransomware");
    expect(getFocusTerm()).toBe("ransomware");
  });

  it("löscht die Auswahl bei null", () => {
    setFocusTerm("ransomware");
    setFocusTerm(null);
    expect(getFocusTerm()).toBeNull();
  });

  it("schreibt in sessionStorage, nicht in localStorage", () => {
    setFocusTerm("phishing");
    expect(sessionStorage.getItem("netzwache.focusTerm")).toBe("phishing");
    expect(localStorage.getItem("netzwache.focusTerm")).toBeNull();
  });

  it("stellt die Auswahl nach einem Reload im selben Tab wieder her", () => {
    // Ein Reload im selben Tab behält sessionStorage bei (im Gegensatz zu
    // In-Memory-State) - hier simuliert durch einen zweiten, unabhängigen
    // Lesevorgang auf demselben Storage-Objekt.
    setFocusTerm("cve-2026-1111");
    expect(getFocusTerm()).toBe("cve-2026-1111");
    expect(getFocusTerm()).toBe("cve-2026-1111");
  });

  it("bleibt zwischen zwei unabhängigen Browser-Sitzungen komplett getrennt", () => {
    const tabA = fakeSessionStorage();
    const tabB = fakeSessionStorage();

    vi.stubGlobal("sessionStorage", tabA);
    setFocusTerm("ransomware");
    expect(getFocusTerm()).toBe("ransomware");

    vi.stubGlobal("sessionStorage", tabB);
    expect(getFocusTerm()).toBeNull(); // Tab B sieht Tab As Auswahl nicht
    setFocusTerm("phishing");
    expect(getFocusTerm()).toBe("phishing");

    vi.stubGlobal("sessionStorage", tabA);
    expect(getFocusTerm()).toBe("ransomware"); // Tab As Auswahl unverändert
  });

  it("wird beim Schließen der Sitzung geleert (neue Sitzung startet leer)", () => {
    setFocusTerm("ransomware");
    expect(getFocusTerm()).toBe("ransomware");

    // Schließen eines Tabs entfernt dessen sessionStorage vollständig - eine
    // neue Sitzung beginnt mit einem frischen, leeren Storage.
    vi.stubGlobal("sessionStorage", fakeSessionStorage());
    expect(getFocusTerm()).toBeNull();
  });

  it("löst niemals einen Netzwerk-Request aus (rein clientseitig)", () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);

    setFocusTerm("ransomware");
    getFocusTerm();
    setFocusTerm(null);

    expect(fetchSpy).not.toHaveBeenCalled();
  });
});

describe("Fokus-Zeitfenster-Speicherung (sessionStorage)", () => {
  it("speichert und liest die Minutenauswahl zurück", () => {
    setFocusWindowMinutes(60);
    expect(getFocusWindowMinutes()).toBe(60);
  });

  it("löscht die Auswahl bei null ('Alle')", () => {
    setFocusWindowMinutes(60);
    setFocusWindowMinutes(null);
    expect(getFocusWindowMinutes()).toBeNull();
  });

  it("übersteht einen Reload im selben Tab", () => {
    setFocusWindowMinutes(1440);
    expect(getFocusWindowMinutes()).toBe(1440);
    expect(getFocusWindowMinutes()).toBe(1440);
  });
});

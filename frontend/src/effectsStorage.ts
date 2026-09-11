/**
 * "Reduzierte Effekte"-Einstellung (schaltet den Weichzeichner/backdrop-filter
 * ab - der teuerste Paint-Effekt auf schwacher/integrierter Grafik). Bewusst
 * localStorage statt eines Server-Felds wie UiSettings: das ist eine
 * Geräte-Eigenschaft (dieser Laptop ist langsam), keine geteilte Präferenz -
 * andere Geräte/Nutzer, die dieselbe Instanz betrachten, sollen davon
 * unberührt bleiben. localStorage statt sessionStorage, damit die Wahl einen
 * Neustart des Browsers übersteht.
 */

const KEY = "netzwache.lowEffects";

/** Ohne explizite Wahl: an, wenn das Betriebssystem "Bewegung reduzieren"
 * verlangt - ein vernünftiger Hinweis auf schwächere/geschonte Hardware,
 * auch ohne dass der Nutzer das Feature hier je gesehen hat. */
function systemPrefersReducedEffects(): boolean {
  try {
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  } catch {
    return false;
  }
}

export function getLowEffects(): boolean {
  try {
    const raw = localStorage.getItem(KEY);
    if (raw !== null) return raw === "1";
  } catch {
    /* Storage nicht verfügbar - Systempräferenz als Fallback */
  }
  return systemPrefersReducedEffects();
}

export function setLowEffects(on: boolean): void {
  try {
    localStorage.setItem(KEY, on ? "1" : "0");
  } catch {
    /* Storage nicht verfügbar - Wahl gilt dann nur für diese Seitenladung */
  }
}

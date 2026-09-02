/**
 * Fokus-Modus-Auswahl ist bewusst pro Tab und temporär: sessionStorage statt
 * localStorage oder eines Server-Felds. sessionStorage ist laut Spezifikation
 * pro Browsing-Context (Tab) isoliert - zwei Tabs auf derselben Seite teilen
 * sich NICHTS, und der Eintrag verschwindet automatisch, wenn der Tab
 * geschlossen wird. Ein Reload im selben Tab behält ihn (deshalb sessionStorage
 * und nicht nur In-Memory-State). Es findet dabei keinerlei Schreibzugriff
 * auf den Server statt - rein clientseitig.
 */

const KEY = "netzwache.focusTerm";
const WINDOW_KEY = "netzwache.focusWindowMinutes";

export function getFocusTerm(): string | null {
  try {
    return sessionStorage.getItem(KEY);
  } catch {
    return null; // z.B. privater Modus ohne Storage-Zugriff
  }
}

export function setFocusTerm(term: string | null): void {
  try {
    if (term) sessionStorage.setItem(KEY, term);
    else sessionStorage.removeItem(KEY);
  } catch {
    /* Storage nicht verfügbar - Fokus bleibt dann nur In-Memory */
  }
}

// Zeitfenster (in Minuten) für die Fokus-Leiste - genau wie der Fokus-Begriff
// selbst pro Tab und über einen Reload hinweg gemerkt, damit man nach dem
// Neuladen nicht wieder durch alle 200 gepufferten Treffer scrollen muss.
export function getFocusWindowMinutes(): number | null {
  try {
    const raw = sessionStorage.getItem(WINDOW_KEY);
    return raw ? Number(raw) : null;
  } catch {
    return null;
  }
}

export function setFocusWindowMinutes(minutes: number | null): void {
  try {
    if (minutes) sessionStorage.setItem(WINDOW_KEY, String(minutes));
    else sessionStorage.removeItem(WINDOW_KEY);
  } catch {
    /* Storage nicht verfügbar - Zeitfenster bleibt dann nur In-Memory */
  }
}

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

/**
 * Wann "trifft" ein Suchbegriff einen Beitrag? - Spiegel von backend/app/enrich.py
 * (term_regex / pg_term_pattern), damit Tagging beim Sammeln, der API-Filter
 * ?term= und der Fokus-Modus für dieselben Daten dieselbe Zahl liefern.
 *
 *  - Der Begriff muss an einer Wortgrenze BEGINNEN ("BSI" trifft "BSI-Warnung",
 *    nicht "we-bsi-te" oder "Ab-si-cherung").
 *  - Danach sind deutsche Endungen/Zusammensetzungen erlaubt ("Sicherheitslücke"
 *    trifft "Sicherheitslücken", "Strompreis" trifft "Strompreisbremse").
 *    Sehr kurze Begriffe (<= 4 Zeichen, z.B. BSI, CVE) erlauben nur ein
 *    optionales Plural-s und müssen danach an einer Wortgrenze enden.
 *  - Leerzeichen und Bindestrich im Begriff sind austauschbar/optional
 *    ("zero-day" trifft "Zero Day"; "open source" trifft "Open-Source").
 *  - Groß-/Kleinschreibung egal; geprüft über Titel + Text + Autor + Quelle.
 */

const SHORT_TERM_MAX_LETTERS = 4;
const WORD_CHAR = "\\p{L}\\p{N}_"; // Unicode-Buchstaben/Ziffern - schließt Umlaute und ß ein

const cache = new Map<string, RegExp | null>();

const escapeRegex = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

export function termRegex(term: string): RegExp | null {
  const hit = cache.get(term);
  if (hit !== undefined) return hit;
  const parts = term.trim().split(/[\s-]+/).filter(Boolean);
  let rx: RegExp | null = null;
  if (parts.length) {
    const body = parts.map(escapeRegex).join("[\\s-]*");
    const letters = parts.reduce((n, p) => n + p.length, 0);
    const tail = letters <= SHORT_TERM_MAX_LETTERS ? `s?(?![${WORD_CHAR}])` : "";
    rx = new RegExp(`(?<![${WORD_CHAR}])${body}${tail}`, "iu");
  }
  cache.set(term, rx);
  return rx;
}

export function containsTerm(haystack: string, term: string): boolean {
  const rx = termRegex(term);
  return rx !== null && rx.test(haystack);
}

/** Die Felder, über die ein Begriff geprüft wird (dieselben wie Volltextsuche und Tagging). */
export function postHaystack(p: { title?: string | null; text?: string | null; author?: string | null; source?: string | null }): string {
  return `${p.title ?? ""} ${p.text ?? ""} ${p.author ?? ""} ${p.source ?? ""}`;
}

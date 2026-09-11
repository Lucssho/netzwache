import type { Post } from "../types";
import { attachExpand, postCard, squareCard, type FeedVariant } from "./feed";

/** Zusätzlicher Renderpuffer oberhalb/unterhalb des sichtbaren Bereichs (px) -
 * verhindert kurzes Weißblitzen beim schnellen Scrollen, bevor recompute()
 * nachzieht. */
const OVERSCAN_PX = 500;

/** Ab dieser Nähe zum Ende der aktuell geladenen (nicht: insgesamt
 * vorhandenen) Treffer wird nachgeladen. */
const NEAR_END_ITEMS = 20;

const EMPTY_NO_FILTER = `
  <div class="empty">
    <span class="big">∅</span>
    Warte auf den ersten Sammellauf …<br>Quellen links anklicken, um sofort zu sammeln.
  </div>`;
const EMPTY_FILTERED = `
  <div class="empty">
    <span class="big">∅</span>
    Keine Treffer für diesen Filter.<br>Filter zurücksetzen oder Suchbegriff ergänzen.
  </div>`;

/**
 * Rendert nur ein Fenster der Liste als echte DOM-Knoten (plus Overscan),
 * unabhängig davon, wie viele Einträge insgesamt geladen sind - der teure
 * Teil eines Feed-Updates (Layout/Paint komplexer Post-Karten) bleibt damit
 * bei 500 wie bei 50.000 Beiträgen konstant klein. Zwei Platzhalter-Divs vor
 * und nach dem gerenderten Fenster geben dem Scroll-Container die korrekte
 * Gesamthöhe, damit sich die Scrollbar normal verhält.
 *
 * Ersetzt das frühere Duo aus vollem innerHTML-Neuaufbau (paintFeed) und
 * separatem inkrementellem insertAdjacentHTML-Pfad für Live-Updates
 * (applyFreshPosts) - mit Virtualisierung ist jedes Update gleich billig,
 * der Sonderfall wird nicht mehr gebraucht.
 */
export class VirtualFeed {
  private items: Post[] = [];
  private hasFilter = false;
  private variant: FeedVariant = "list";
  private knownIds = new Set<number>();

  // Läuft nach jedem Render mit den tatsächlich gemessenen Kartenhöhen nach -
  // Post-Karten sind unterschiedlich hoch (Titel/Text/Badges variieren), eine
  // gleitende Schätzung reicht für eine stabile Scrollbar-Position.
  private estItemHeight = 190;

  private renderedStart = -1;
  private renderedEnd = -1;
  private throttleHandle: ReturnType<typeof setTimeout> | null = null;
  private readonly resizeObserver: ResizeObserver;

  private readonly topSpacer: HTMLDivElement;
  private readonly bottomSpacer: HTMLDivElement;

  constructor(
    private readonly scrollEl: HTMLElement,
    private readonly listEl: HTMLElement,
    private readonly onNearEnd: () => void,
  ) {
    this.topSpacer = document.createElement("div");
    this.topSpacer.className = "feed-vspacer";
    this.bottomSpacer = document.createElement("div");
    this.bottomSpacer.className = "feed-vspacer";
    this.scrollEl.addEventListener("scroll", this.scheduleRecompute);
    // window "resize" allein reicht nicht: der Scroll-Container kann seine
    // Höhe auch durch eigenes Layout-Settling ändern (z.B. beim initialen
    // Boot, bevor umliegende Panels ihre endgültige Größe haben) - ohne
    // ResizeObserver bliebe das Fenster dann dauerhaft auf Basis einer zu
    // kleinen clientHeight zu klein berechnet.
    this.resizeObserver = new ResizeObserver(this.scheduleRecompute);
    this.resizeObserver.observe(this.scrollEl);
  }

  /** Neue Datenlage (Filterwechsel, Live-Update, Nachladen, Variantenwechsel) -
   * berechnet nur das sichtbare Fenster neu, nie die komplette Liste. */
  update(items: Post[], hasFilter: boolean, variant: FeedVariant): void {
    const variantChanged = variant !== this.variant;
    this.items = items;
    this.hasFilter = hasFilter;
    this.variant = variant;
    if (variantChanged) {
      this.listEl.classList.toggle("variant-grid", variant === "grid");
      this.renderedStart = this.renderedEnd = -1; // erzwingt vollen Rebuild des Fensters
      // Listen- und Kachel-Layout haben stark unterschiedliche Zeilenhöhen -
      // ein scrollTop, das im alten Layout gültig war, kann im neuen weit
      // hinter dem tatsächlichen Ende liegen und ein leeres Fenster ergeben.
      this.scrollEl.scrollTop = 0;
    }
    this.recompute(true);
  }

  /** Anzahl der aktuell (im internen state.posts-Sinn) verfügbaren Treffer -
   * für die "X sichtbar / Y im Puffer"-Anzeige in main.ts. */
  get totalCount(): number {
    return this.items.length;
  }

  destroy(): void {
    this.scrollEl.removeEventListener("scroll", this.scheduleRecompute);
    this.resizeObserver.disconnect();
    if (this.throttleHandle != null) clearTimeout(this.throttleHandle);
  }

  // setTimeout statt requestAnimationFrame: rAF wird von Browsern für nicht
  // sichtbare/nicht fokussierte Tabs komplett ausgesetzt (nicht nur
  // gedrosselt) - ein Nutzer, der zwischen Tabs wechselt und zurückkommt,
  // hätte sonst ein Fenster, das seit dem letzten Scroll vor dem Wechsel
  // nicht mehr aktualisiert wurde. ~1 Frame Verzögerung ist für dieses
  // Nachrendern unkritisch.
  private scheduleRecompute = (): void => {
    if (this.throttleHandle != null) return;
    this.throttleHandle = setTimeout(() => {
      this.throttleHandle = null;
      this.recompute(false);
    }, 16);
  };

  private columnsPerRow(): number {
    if (this.variant !== "grid") return 1;
    // Muss zu .feed.variant-grid { grid-template-columns: repeat(auto-fill, minmax(140px,1fr)); gap: 8px; } passen.
    const minTile = 140;
    const gap = 8;
    const width = this.listEl.clientWidth || minTile;
    return Math.max(1, Math.floor((width + gap) / (minTile + gap)));
  }

  private gridRowHeight(cols: number): number {
    // .post-square hat aspect-ratio: 1 -> Höhe der Kachel == ihre Breite.
    const gap = 8;
    const width = this.listEl.clientWidth || cols * 140;
    const tileWidth = (width - gap * (cols - 1)) / cols;
    return tileWidth + gap;
  }

  private recompute(force: boolean): void {
    if (!this.items.length) {
      if (force) {
        this.listEl.innerHTML = this.hasFilter ? EMPTY_FILTERED : EMPTY_NO_FILTER;
        this.renderedStart = this.renderedEnd = -1;
      }
      return;
    }

    const cols = this.columnsPerRow();
    const rowHeight = this.variant === "grid" ? this.gridRowHeight(cols) : this.estItemHeight;
    const rowCount = Math.ceil(this.items.length / cols);

    const viewportH = this.scrollEl.clientHeight || 600;
    // scrollTop kann kurzzeitig zu einem Layout gehören, das nicht mehr
    // gültig ist (z.B. Wechsel Liste/Kacheln mit stark unterschiedlicher
    // Zeilenhöhe, oder ein Filterwechsel, der die Trefferzahl bei tief
    // gescrollter Position stark schrumpft) - der DOM-eigene scrollTop passt
    // sich erst mit der nächsten Layout-Runde an. Auf die für die aktuellen
    // Daten maximal sinnvolle Position klemmen, sonst ergäbe sich ein Fenster
    // hinter dem letzten Eintrag und damit eine leere Liste.
    const maxScrollTop = Math.max(0, rowCount * rowHeight - viewportH);
    const scrollTop = Math.min(this.scrollEl.scrollTop, maxScrollTop);

    const startRow = Math.max(0, Math.floor((scrollTop - OVERSCAN_PX) / rowHeight));
    const endRow = Math.min(rowCount, Math.ceil((scrollTop + viewportH + OVERSCAN_PX) / rowHeight));

    const startIdx = startRow * cols;
    const endIdx = Math.min(this.items.length, endRow * cols);

    if (!force && startIdx === this.renderedStart && endIdx === this.renderedEnd) {
      this.checkNearEnd(endIdx);
      return;
    }

    const slice = this.items.slice(startIdx, endIdx);
    const html =
      this.variant === "grid"
        ? slice.map((p) => squareCard(p)).join("")
        : slice.map((p) => postCard(p, !this.knownIds.has(p.id))).join("");

    this.listEl.innerHTML = "";
    this.topSpacer.style.height = `${startRow * rowHeight}px`;
    this.bottomSpacer.style.height = `${(rowCount - endRow) * rowHeight}px`;
    this.listEl.appendChild(this.topSpacer);
    this.topSpacer.insertAdjacentHTML("afterend", html);
    this.listEl.appendChild(this.bottomSpacer);
    if (this.variant === "list") attachExpand(this.listEl);

    this.renderedStart = startIdx;
    this.renderedEnd = endIdx;
    this.knownIds = new Set(this.items.map((p) => p.id));

    // Erst NACH diesem Frame messen (requestAnimationFrame), nicht sofort:
    // getBoundingClientRect() direkt nach einer DOM-Schreiboperation erzwingt
    // einen synchronen Reflow on-the-spot - gemessen ~6-24ms pro Aufruf, und
    // das bei JEDEM Recompute (auch beim Scrollen). Verschoben auf den
    // nächsten Frame liest es Werte, die der Browser ohnehin gerade berechnet
    // hat, ohne einen zusätzlichen erzwungenen Reflow im kritischen Pfad.
    if (this.variant === "list") requestAnimationFrame(() => this.refineHeightEstimate());

    this.checkNearEnd(endIdx);
  }

  private refineHeightEstimate(): void {
    const nodes = this.listEl.querySelectorAll<HTMLElement>(":scope > .post");
    if (!nodes.length) return;
    let sum = 0;
    nodes.forEach((n) => (sum += n.getBoundingClientRect().height));
    const gapPx = 10; // ~ var(--gap-feed), grob genug für die Schätzung
    const measured = sum / nodes.length + gapPx;
    // Gleitender Mittelwert statt hartem Ersetzen - vermeidet Sprünge in der
    // Scrollbar-Höhe, wenn eine einzelne besonders kurze/lange Karte im
    // aktuellen Fenster landet.
    this.estItemHeight = this.estItemHeight * 0.6 + measured * 0.4;
  }

  private checkNearEnd(endIdx: number): void {
    if (endIdx >= this.items.length - NEAR_END_ITEMS) this.onNearEnd();
  }
}

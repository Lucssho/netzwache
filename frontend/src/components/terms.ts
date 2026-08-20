import type { Term } from "../types";
import { esc } from "../utils";

const CATEGORIES = ["cybersecurity", "it", "nachrichten", "alltag"];
const CATEGORY_LABEL: Record<string, string> = {
  cybersecurity: "cybersecurity",
  it: "it",
  nachrichten: "news",
  alltag: "alltag",
};

// Bleibt über Re-Renders hinweg erhalten (Filterbox wird bei jedem paintTerms()
// neu ins DOM geschrieben), damit Tippen nicht bei jeder Aktion verloren geht.
let tagSearch = "";

export function renderTerms(
  el: HTMLElement,
  terms: Term[],
  handlers: {
    onAdd: (term: string, category: string) => void;
    onDelete: (id: number) => void;
    onToggle: (id: number, enabled: boolean) => void;
    onFocus: (term: string) => void;
  },
  focusTerm: string | null,
  freshId?: number,
): void {
  const q = tagSearch.trim().toLowerCase();
  const visibleTerms = q ? terms.filter((t) => t.term.toLowerCase().includes(q)) : terms;

  el.innerHTML = `
    <div class="term-controls-sticky">
      <form class="term-input" id="term-form" autocomplete="off">
        <input id="term-input" placeholder="neuer Suchbegriff …" maxlength="120" />
        <select id="term-cat">
          ${CATEGORIES.map((c) => `<option value="${c}">${CATEGORY_LABEL[c]}</option>`).join("")}
        </select>
        <button type="submit" class="btn-go" title="Begriff hinzufügen und sofort danach suchen">+</button>
      </form>
      ${
        terms.length > 6
          ? `<div class="term-search-wrap">
               <input id="term-search" class="term-search" placeholder="Tags filtern …" value="${esc(tagSearch)}" autocomplete="off" />
               <button type="button" id="term-search-clear" class="term-search-clear" title="Filter zurücksetzen" style="display:${tagSearch ? "flex" : "none"}">×</button>
             </div>`
          : ""
      }
    </div>
    <div class="terms ${focusTerm ? "focus-active" : ""}">
      ${
        visibleTerms.length
          ? visibleTerms
              .map((t) => {
                const focused = t.term === focusTerm;
                return `
        <span class="chip ${esc(t.category)} ${t.enabled ? "" : "off"} ${t.id === freshId ? "fresh" : ""} ${focused ? "focused" : ""}"
              data-id="${t.id}" data-term="${esc(t.term)}" title="Klick: nur diesen Begriff anzeigen">
          <span class="tg" title="an/aus">${t.enabled ? "●" : "○"}</span>
          <span class="lbl">${esc(t.term)}</span>
          <span class="hits">${t.hits}</span>
          <span class="x" title="löschen">×</span>
        </span>`;
              })
              .join("")
          : `<div class="empty">${
              terms.length ? "Kein Tag passt zum Filter." : "Noch keine Suchbegriffe."
            }</div>`
      }
    </div>`;

  const form = el.querySelector<HTMLFormElement>("#term-form")!;
  const input = el.querySelector<HTMLInputElement>("#term-input")!;
  const cat = el.querySelector<HTMLSelectElement>("#term-cat")!;
  const search = el.querySelector<HTMLInputElement>("#term-search");
  const searchClear = el.querySelector<HTMLButtonElement>("#term-search-clear");

  form.addEventListener("submit", (ev) => {
    ev.preventDefault();
    const value = input.value.trim();
    if (value.length < 2) return;
    handlers.onAdd(value, cat.value);
    input.value = "";
  });

  search?.addEventListener("input", () => {
    tagSearch = search.value;
    const term = tagSearch.trim().toLowerCase();
    el.querySelectorAll<HTMLElement>(".chip").forEach((chip) => {
      chip.style.display = !term || (chip.dataset.term ?? "").toLowerCase().includes(term) ? "" : "none";
    });
    if (searchClear) searchClear.style.display = tagSearch ? "flex" : "none";
  });
  search?.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape" && search.value) {
      ev.stopPropagation();
      search.value = "";
      tagSearch = "";
      search.dispatchEvent(new Event("input"));
    }
  });
  searchClear?.addEventListener("click", () => {
    tagSearch = "";
    // "Alle Tags wieder sehen" heißt auch: einen aktiven Fokus aufheben -
    // sonst bleiben trotz zurückgesetztem Text alle anderen Chips gedimmt.
    // onFocus löst ein volles Re-Render aus, das die Suchbox mit dem jetzt
    // leeren tagSearch neu aufbaut - also erst danach den frischen Knoten holen.
    if (focusTerm) {
      handlers.onFocus(focusTerm);
      el.querySelector<HTMLInputElement>("#term-search")?.focus();
    } else if (search) {
      search.value = "";
      search.dispatchEvent(new Event("input"));
      search.focus();
    }
  });

  el.querySelectorAll<HTMLElement>(".chip").forEach((chip) => {
    const id = Number(chip.dataset.id);
    const term = terms.find((t) => t.id === id);
    chip.querySelector(".x")?.addEventListener("click", (ev) => {
      ev.stopPropagation();
      handlers.onDelete(id);
    });
    chip.querySelector(".tg")?.addEventListener("click", (ev) => {
      ev.stopPropagation();
      if (term) handlers.onToggle(id, !term.enabled);
    });
    chip.addEventListener("click", () => {
      if (term) handlers.onFocus(term.term);
    });
  });
}

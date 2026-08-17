import type { Term } from "../types";
import { esc } from "../utils";

const CATEGORIES = ["cybersecurity", "it", "nachrichten", "alltag"];
const CATEGORY_LABEL: Record<string, string> = {
  cybersecurity: "cybersecurity",
  it: "it",
  nachrichten: "news",
  alltag: "alltag",
};

export function renderTerms(
  el: HTMLElement,
  terms: Term[],
  handlers: {
    onAdd: (term: string, category: string) => void;
    onDelete: (id: number) => void;
    onToggle: (id: number, enabled: boolean) => void;
  },
  freshId?: number,
): void {
  el.innerHTML = `
    <form class="term-input" id="term-form" autocomplete="off">
      <input id="term-input" placeholder="neuer Suchbegriff …" maxlength="120" />
      <select id="term-cat">
        ${CATEGORIES.map((c) => `<option value="${c}">${CATEGORY_LABEL[c]}</option>`).join("")}
      </select>
      <button type="submit" class="btn-go" title="Begriff hinzufügen und sofort danach suchen">+</button>
    </form>
    <div class="terms">
      ${
        terms.length
          ? terms
              .map(
                (t) => `
        <span class="chip ${esc(t.category)} ${t.enabled ? "" : "off"} ${t.id === freshId ? "fresh" : ""}" data-id="${t.id}">
          <span class="tg" title="an/aus">${t.enabled ? "●" : "○"}</span>
          ${esc(t.term)}
          <span class="hits">${t.hits}</span>
          <span class="x" title="löschen">×</span>
        </span>`,
              )
              .join("")
          : `<div class="empty">Noch keine Suchbegriffe.</div>`
      }
    </div>`;

  const form = el.querySelector<HTMLFormElement>("#term-form")!;
  const input = el.querySelector<HTMLInputElement>("#term-input")!;
  const cat = el.querySelector<HTMLSelectElement>("#term-cat")!;

  form.addEventListener("submit", (ev) => {
    ev.preventDefault();
    const value = input.value.trim();
    if (value.length < 2) return;
    handlers.onAdd(value, cat.value);
    input.value = "";
  });

  el.querySelectorAll<HTMLElement>(".chip").forEach((chip) => {
    const id = Number(chip.dataset.id);
    const term = terms.find((t) => t.id === id);
    chip.querySelector(".x")?.addEventListener("click", () => handlers.onDelete(id));
    chip.querySelector(".tg")?.addEventListener("click", () => {
      if (term) handlers.onToggle(id, !term.enabled);
    });
  });
}

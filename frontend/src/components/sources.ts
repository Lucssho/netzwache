import { PLATFORM_LABEL, platformIcon } from "../icons";
import type { SourceState } from "../types";
import { esc, num, relTime } from "../utils";

const LED: Record<string, string> = {
  ok: "ok",
  idle: "warn",
  error: "err",
  disabled: "off",
  degraded: "warn",
};

const STATUS_TEXT: Record<string, string> = {
  ok: "läuft",
  idle: "wartet",
  error: "Fehler",
  disabled: "inaktiv",
  degraded: "eingeschränkt",
};

export function renderSources(
  el: HTMLElement,
  sources: SourceState[],
  activePlatforms: Set<string> | null,
  onToggle: (name: string, enabled: boolean) => void,
  onCollect: (name: string) => void,
): void {
  if (!sources.length) {
    el.innerHTML = `<div class="empty">Keine Quellen registriert.</div>`;
    return;
  }

  el.innerHTML = sources
    .map((s) => {
      const led = LED[s.status] ?? "off";
      const inactive = s.status === "disabled";
      const detail = inactive && s.setup_hint ? s.setup_hint : s.detail;
      const dim = activePlatforms && !activePlatforms.has(s.platform);
      return `
      <div class="source ${s.enabled ? "" : "disabled"} ${s.status === "error" ? "err" : ""} ${dim ? "dim" : ""}"
           data-name="${esc(s.name)}" title="Klick: Sofort sammeln &middot; Rechtsklick: an/aus">
        <span class="led ${led}"></span>
        <div>
          <div class="nm">
            <span class="pbadge ${esc(s.platform)}">${platformIcon(s.platform, 12)}<span>${esc(PLATFORM_LABEL[s.platform] ?? s.platform)}</span></span>
            ${esc(s.label)}
          </div>
          <div class="meta">
            ${STATUS_TEXT[s.status] ?? s.status} &middot; alle ${s.interval_seconds}s
            ${s.last_run_at ? `&middot; ${relTime(s.last_run_at)}` : ""}
            ${detail ? `<br>${esc(detail).slice(0, 150)}` : ""}
          </div>
        </div>
        <div class="num">
          ${num(s.items_total)}
          <small>${s.items_last_run > 0 ? `+${s.items_last_run}` : "gesamt"}</small>
        </div>
      </div>`;
    })
    .join("");

  el.querySelectorAll<HTMLElement>(".source").forEach((node) => {
    const name = node.dataset.name!;
    node.addEventListener("click", () => onCollect(name));
    node.addEventListener("contextmenu", (ev) => {
      ev.preventDefault();
      const src = sources.find((x) => x.name === name);
      if (src) onToggle(name, !src.enabled);
    });
  });
}

import type { Diagnostics } from "../types";
import { esc } from "../utils";

const PLATFORM_LABEL: Record<string, string> = {
  bluesky: "Bluesky",
  reddit: "Reddit",
  x: "X / Twitter",
  facebook: "Facebook",
};

export function renderDiagnosticsPanel(el: HTMLElement, d: Diagnostics | null): void {
  if (!d) {
    el.innerHTML = `<h4>Diagnose</h4><div class="diag-row"><span class="lbl">lädt …</span></div>`;
    return;
  }

  el.innerHTML = `
    <h4>System</h4>
    <div class="diag-row">
      <span class="lbl">Datenbank</span>
      <span class="val ${d.database.ok ? "ok" : "bad"}">${d.database.ok ? "verbunden" : "Fehler"} · ${esc(d.database.engine)}</span>
    </div>
    <div class="diag-row">
      <span class="lbl">Deduplizierung</span>
      <span class="val ${d.redis.connected ? "ok" : ""}">${d.redis.connected ? "Redis" : "In-Memory (Fallback)"}</span>
    </div>
    <div class="diag-row">
      <span class="lbl">Live-Verbindungen</span>
      <span class="val">${d.websocket_clients}</span>
    </div>

    <h4 style="margin-top:13px">Zugangsdaten</h4>
    ${Object.entries(d.credentials)
      .map(
        ([platform, c]) => `
      <div class="diag-row">
        <span class="lbl">${esc(PLATFORM_LABEL[platform] ?? platform)}</span>
        <span class="val ${c.configured ? "ok" : ""}">${c.configured ? "eingerichtet" : "nicht konfiguriert"}${c.mode ? ` · ${esc(c.mode)}` : ""}</span>
      </div>`,
      )
      .join("")}

    <h4 style="margin-top:13px">Bekannte Stolpersteine</h4>
    ${d.known_issues
      .map(
        (i) => `
      <details class="issue">
        <summary>${esc(i.title)}</summary>
        <div class="body">
          <b>Anzeichen:</b> ${esc(i.symptom)}<br><br>
          <b>Lösung:</b> ${esc(i.fix)}
        </div>
      </details>`,
      )
      .join("")}
  `;
}

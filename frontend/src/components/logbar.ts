import type { LogEntry } from "../types";
import { esc, num } from "../utils";

export function renderLogbar(
  el: HTMLElement,
  entry: LogEntry | null,
  info: { dedup: string; ws: number; total: number; ticks: number },
): void {
  const time = entry?.ts ? new Date(entry.ts).toLocaleTimeString("de-DE", { hour12: false }) : "--:--:--";
  el.innerHTML = `
    <span class="lvl ${esc(entry?.level ?? "info")}">[${esc((entry?.level ?? "boot").toUpperCase())}]</span>
    <span style="color:var(--dimmer)">${time}</span>
    <span style="color:var(--green)">${esc(entry?.source ?? "core")}</span>
    <span class="msg">${esc(entry?.message ?? "NETZWACHE bereit – warte auf Sammellauf …")}</span>
    <span class="right">
      <span>dedup: ${esc(info.dedup)}</span>
      <span>ws-clients: ${info.ws}</span>
      <span>ticks: ${num(info.ticks)}</span>
      <span>db: ${num(info.total)} posts</span>
    </span>`;
}

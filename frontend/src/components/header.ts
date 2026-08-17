import type { Stats } from "../types";
import { clock, num, uptime } from "../utils";

export function renderHeader(
  el: HTMLElement,
  s: {
    stats: Stats | null;
    connected: boolean;
    nextTick: number;
    tickSeconds: number;
    filterLabel: string;
  },
): void {
  const pct = s.tickSeconds ? 1 - s.nextTick / s.tickSeconds : 0;
  const c = 2 * Math.PI * 18;
  const total = s.stats?.total ?? 0;

  el.innerHTML = `
    <div class="brand">
      <div class="brand-text">
        <h1>CYBER DOME</h1>
        <div class="sub">Multi-Plattform Lagebild &middot; OSINT Collector</div>
      </div>
    </div>

    <div class="prompt">
      <b>root@netzwache</b>:<b>~</b># collect --sources=all --filter=${s.filterLabel}<span class="cursor"></span>
    </div>

    <div class="head-stats">
      <div class="hstat">
        <div class="k">Uhrzeit</div>
        <div class="v">${clock()}</div>
      </div>
      <div class="hstat">
        <div class="k">Laufzeit</div>
        <div class="v amber">${uptime(s.stats?.uptime_seconds ?? 0)}</div>
      </div>
      <div class="hstat">
        <div class="k">Beiträge gesamt</div>
        <div class="v green">${num(total)}</div>
      </div>
      <div class="hstat">
        <div class="k">Stream</div>
        <div class="v">
          <span class="led ${s.connected ? "ok pulse" : "err"}"></span>
          <span style="font-size:0.92rem">${s.connected ? "LIVE" : "OFFLINE"}</span>
        </div>
      </div>
      <div class="tick-ring" title="Nächster Sammellauf">
        <svg width="46" height="46">
          <circle cx="23" cy="23" r="18" stroke="#1b2830" stroke-width="3" fill="none"/>
          <circle cx="23" cy="23" r="18" stroke="#4ee07a" stroke-width="3" fill="none"
                  stroke-linecap="round"
                  stroke-dasharray="${c}" stroke-dashoffset="${c * (1 - pct)}"/>
        </svg>
        <div class="val">${s.nextTick}s</div>
      </div>
    </div>`;
}

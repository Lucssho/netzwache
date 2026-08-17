import type { Stats } from "../types";
import { clock, num, uptime } from "../utils";

const SHIELD = `
<svg width="42" height="46" viewBox="0 0 42 46" fill="none" aria-hidden="true">
  <defs>
    <linearGradient id="flag" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#141414"/>
      <stop offset="45%" stop-color="#c8102e"/>
      <stop offset="100%" stop-color="#ffcc00"/>
    </linearGradient>
  </defs>
  <path d="M21 2 3 8v14c0 12 8 18.5 18 22 10-3.5 18-10 18-22V8z"
        fill="#0b1114" stroke="url(#flag)" stroke-width="2.2"/>
  <path d="M21 6.5 7 11v11c0 9.6 6.4 14.8 14 17.7 7.6-2.9 14-8.1 14-17.7V11z"
        fill="none" stroke="#4ee07a" stroke-width="1" opacity="0.45"/>
  <path d="M13 22.5h16M21 14.5v16" stroke="#4ee07a" stroke-width="2.4" stroke-linecap="round"/>
  <circle cx="21" cy="22.5" r="4.4" fill="none" stroke="#4ee07a" stroke-width="1.4" opacity="0.8"/>
</svg>`;

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
      ${SHIELD}
      <div class="brand-text">
        <h1>NETZWACHE</h1>
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

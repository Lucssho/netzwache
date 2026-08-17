import { PLATFORM_LABEL, platformIcon } from "../icons";
import type { Stats } from "../types";
import { esc, num } from "../utils";

export function renderStats(el: HTMLElement, s: Stats | null): void {
  if (!s) {
    el.innerHTML = `<div class="empty">Lade Kennzahlen …</div>`;
    return;
  }

  const max = Math.max(1, ...s.series);
  const platforms = Object.entries(s.by_platform).sort((a, b) => b[1] - a[1]);
  const pMax = Math.max(1, ...platforms.map(([, n]) => n));
  const categories = Object.entries(s.by_category).sort((a, b) => b[1] - a[1]);
  const cMax = Math.max(1, ...categories.map(([, n]) => n));

  el.innerHTML = `
    <div class="kpis">
      <div class="kpi"><div class="k">Letzte Stunde</div><div class="v">${num(s.last_hour)}</div></div>
      <div class="kpi"><div class="k">Letzte 5 min</div><div class="v">${num(s.last_5min)}</div></div>
      <div class="kpi"><div class="k">Pro Minute</div><div class="v small">${s.per_minute.toFixed(2)}</div></div>
      <div class="kpi"><div class="k">Hohe Severity</div><div class="v small ${s.high_severity ? "red" : ""}">${num(s.high_severity)}</div></div>
    </div>

    <div style="margin-top:12px">
      <div class="k" style="font-size:0.69rem;letter-spacing:.13em;color:var(--dimmer);text-transform:uppercase">
        Beiträge / Minute (30 min)
      </div>
      <div class="spark">
        ${s.series
          .map(
            (v) =>
              `<i style="height:${v ? Math.max(6, (v / max) * 100) : 2}%;opacity:${v ? 1 : 0.28}" title="${v} Beiträge"></i>`,
          )
          .join("")}
      </div>
    </div>

    <div style="margin-top:14px">
      <div class="k" style="font-size:0.69rem;letter-spacing:.13em;color:var(--dimmer);text-transform:uppercase;margin-bottom:6px">
        Nach Plattform
      </div>
      ${platforms
        .map(
          ([p, n]) => `
        <div class="bar-row">
          <span class="pbadge ${esc(p)}">${platformIcon(p, 11)}<span>${esc(PLATFORM_LABEL[p] ?? p)}</span></span>
          <span class="bar"><i class="${esc(p)}" style="width:${(n / pMax) * 100}%"></i></span>
          <span class="n">${num(n)}</span>
        </div>`,
        )
        .join("")}
    </div>

    <div style="margin-top:14px">
      <div class="k" style="font-size:0.69rem;letter-spacing:.13em;color:var(--dimmer);text-transform:uppercase;margin-bottom:6px">
        Nach Thema (letzte 600)
      </div>
      ${categories
        .map(
          ([c, n]) => `
        <div class="bar-row">
          <span class="cat ${esc(c)}">${esc(c).slice(0, 8)}</span>
          <span class="bar"><i style="width:${(n / cMax) * 100}%"></i></span>
          <span class="n">${num(n)}</span>
        </div>`,
        )
        .join("")}
    </div>

    ${
      s.top_cves.length
        ? `<div style="margin-top:14px">
             <div class="k" style="font-size:0.69rem;letter-spacing:.13em;color:var(--dimmer);text-transform:uppercase;margin-bottom:6px">
               CVE-Watch
             </div>
             <div class="kw">
               ${s.top_cves.map(([c, n]) => `<span class="cve">${esc(c)} <b style="opacity:.6">×${n}</b></span>`).join("")}
             </div>
           </div>`
        : ""
    }

    <div style="margin-top:14px">
      <div class="k" style="font-size:0.69rem;letter-spacing:.13em;color:var(--dimmer);text-transform:uppercase;margin-bottom:6px">
        Häufige Begriffe
      </div>
      <div class="kw">
        ${s.top_keywords.map(([k, n]) => `<span>${esc(k)}<b>${n}</b></span>`).join("")}
      </div>
    </div>`;
}

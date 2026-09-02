import "./styles.css";

import { api } from "./api";
import { attachExpand, postCard, renderFeed, type FeedVariant } from "./components/feed";
import { renderHeader } from "./components/header";
import { applySettings } from "./components/settingsPanel";
import { renderSources } from "./components/sources";
import { renderStats } from "./components/stats";
import { renderTerms } from "./components/terms";
import {
  getFocusTerm as getStoredFocusTerm,
  getFocusWindowMinutes as getStoredFocusWindowMinutes,
  setFocusTerm as persistFocusTerm,
  setFocusWindowMinutes as persistFocusWindowMinutes,
} from "./focusStorage";
import { platformIcon } from "./icons";
import type { Filters, Post, SourceState, Stats, Term, UiSettings } from "./types";
import { esc, restrictToAlnum } from "./utils";
import { LiveStream } from "./ws";

const MAX_BUFFER = 400;

const DEFAULT_SETTINGS: UiSettings = {
  font_family: "jetbrains",
  font_size: "13",
  density: "comfortable",
  theme: "dark",
};

const state = {
  posts: [] as Post[],
  sources: [] as SourceState[],
  terms: [] as Term[],
  stats: null as Stats | null,
  connected: false,
  tickSeconds: 10,
  nextTick: 10,
  settings: { ...DEFAULT_SETTINGS } as UiSettings,
  isAdmin: false,
  sourcesOpen: false,
  leftColOpen: false,
  lagebildOpen: false,
  feedVariant: "list" as FeedVariant,
  resurfacedPostId: null as number | null,
  resurfaceActive: false,
  stallStreak: {} as Record<string, number>,
  filters: {
    platform: "all",
    category: "cybersecurity",
    query: "",
    minSeverity: 0,
    paused: false,
    focusTerm: getStoredFocusTerm(),
    focusWindowMinutes: getStoredFocusWindowMinutes(),
  } as Filters,
};

// Sofort anwenden (aus lokalem Fallback), bevor überhaupt ein Request raus ist -
// verhindert einen kurzen Blitz mit der Standardschrift.
applySettings(state.settings);

// ---------------------------------------------------------------- Gerüst
const app = document.getElementById("app")!;
app.innerHTML = `
  <header class="top">
    <div class="traffic" title="CYBER SHIELD">
      <i class="tr-red"></i><i class="tr-amber"></i><i class="tr-green" id="tr-green"></i>
    </div>
    <div id="header-inner"></div>
  </header>

  <div class="filterbar">
    <div class="tabs" id="tab-platform"></div>
    <div class="tabs" id="tab-category"></div>
    <div class="search-wrap">
      <input id="search" placeholder="Volltextsuche im Feed …" autocomplete="off" />
    </div>
    <button id="btn-pause" class="btn-ghost" title="Live-Stream anhalten (Leertaste)">⏸ Pause</button>
    <button id="btn-collect" class="btn-go" title="Alle Quellen sofort abfragen">▶ Jetzt sammeln</button>

    <button id="btn-theme" class="theme-switch" type="button" title="Design umschalten" role="switch" aria-checked="false">
      <svg class="ts-icon ts-moon" width="11" height="11" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path d="M21 12.8A9 9 0 1 1 11.2 3 7 7 0 0 0 21 12.8Z" fill="currentColor"/>
      </svg>
      <svg class="ts-icon ts-sun" width="11" height="11" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <circle cx="12" cy="12" r="5" stroke="currentColor" stroke-width="2"/>
        <path d="M12 1v3M12 20v3M4.2 4.2l2.1 2.1M17.7 17.7l2.1 2.1M1 12h3M20 12h3M4.2 19.8l2.1-2.1M17.7 6.3l2.1-2.1" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
      </svg>
      <span class="theme-switch-knob"></span>
    </button>

    <div class="admin-login-anchor">
      <button id="btn-admin" class="btn-ghost" type="button" title="Admin-Anmeldung">Admin</button>
      <form id="admin-login-form" class="admin-login" style="display:none" autocomplete="off">
        <input id="admin-user" placeholder="Benutzername" autocomplete="username" />
        <input id="admin-pass" type="password" placeholder="Passwort" autocomplete="current-password" />
        <button type="submit" class="btn-go">Anmelden</button>
        <div class="admin-login-err" id="admin-login-err"></div>
      </form>
    </div>
  </div>

  <div class="main left-collapsed right-collapsed" id="main-grid">
    <div class="col col-left">
      <div class="col-outer collapsed" id="col-outer-left">
        <div class="col-outer-head">
          <span class="panel-title" id="left-outer-title">Suchraum</span>
          <button id="btn-leftcol-toggle" class="icon-btn collapse-toggle flip" title="Suchraum ein-/ausblenden">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
              <path d="M7 3.5 3.5 7l3.5 3.5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>
              <path d="M10.5 3.5 7 7l3.5 3.5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
          </button>
        </div>
        <div class="col-outer-body" id="left-outer-body">
          <section class="panel" style="flex:1 1 auto">
            <div class="panel-head">
              <span class="panel-title">Suchbegriffe</span>
              <span style="font-size:0.73rem;color:var(--dimmer)" id="term-count"></span>
            </div>
            <div class="panel-body">
              <div id="term-status" class="term-status"></div>
              <div id="terms"></div>
            </div>
          </section>
          <section class="panel" style="flex:1 1 auto">
            <div class="panel-head">
              <span class="panel-title">Quellen</span>
              <button id="btn-sources-toggle" class="icon-btn lg chevron" title="Quellen ein-/ausblenden">
                <svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true">
                  <path d="M3 4 6 8l3-4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
              </button>
            </div>
            <div class="panel-body tight collapsed" id="sources"></div>
          </section>
        </div>
      </div>
    </div>

    <div class="col">
      <section class="panel" style="flex:1 1 auto">
        <div class="panel-head">
          <span class="panel-title">Live-Feed</span>
          <div style="display:flex;align-items:center;gap:10px">
            <span style="font-size:0.73rem;color:var(--dimmer)" id="feed-info"></span>
            <div class="seg" id="feed-variant-toggle">
              <button type="button" data-v="list" class="active" title="Liste">☰</button>
              <button type="button" data-v="grid" title="Kacheln">▦</button>
            </div>
          </div>
        </div>
        <div class="focus-bar" id="focus-bar" style="display:none">
          <span class="focus-bar-label">Fokus auf <b id="focus-bar-term"></b><span id="focus-bar-count"></span></span>
          <div class="seg focus-window-toggle" id="focus-window-toggle" title="Nur Treffer aus diesem Zeitraum zeigen">
            <button type="button" data-min="5" title="letzte 5 Minuten">Jetzt</button>
            <button type="button" data-min="60" title="letzte Stunde">1 Std</button>
            <button type="button" data-min="1440" title="letzte 24 Stunden">24 Std</button>
            <button type="button" data-min="0" class="active" title="kein Zeitfilter">Alle</button>
          </div>
          <button type="button" id="focus-bar-clear" title="Fokus aufheben (Esc)">Fokus aufheben ✕</button>
        </div>
        <div class="panel-body tight" id="feed-scroll">
          <div class="feed" id="feed"></div>
        </div>
      </section>
    </div>

    <div class="col col-right">
      <section class="panel" style="flex:1 1 auto">
        <div class="panel-head">
          <span class="panel-title" id="lagebild-title" style="display:none">Lagebild</span>
          <button id="btn-lagebild-toggle" class="icon-btn collapse-toggle" title="Lagebild ein-/ausblenden">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
              <path d="M7 3.5 3.5 7l3.5 3.5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>
              <path d="M10.5 3.5 7 7l3.5 3.5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
          </button>
        </div>
        <div class="panel-body collapsed" id="stats"></div>
      </section>
    </div>
  </div>

  <div class="toast-wrap" id="toasts"></div>
`;

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const els = {
  headerInner: $("header-inner"),
  trGreen: $("tr-green"),
  tabPlatform: $("tab-platform"),
  tabCategory: $("tab-category"),
  search: $<HTMLInputElement>("search"),
  btnPause: $<HTMLButtonElement>("btn-pause"),
  btnCollect: $<HTMLButtonElement>("btn-collect"),
  btnTheme: $<HTMLButtonElement>("btn-theme"),
  btnAdmin: $<HTMLButtonElement>("btn-admin"),
  adminLoginForm: $<HTMLFormElement>("admin-login-form"),
  adminUser: $<HTMLInputElement>("admin-user"),
  adminPass: $<HTMLInputElement>("admin-pass"),
  adminLoginErr: $("admin-login-err"),
  sources: $("sources"),
  btnSourcesToggle: $<HTMLButtonElement>("btn-sources-toggle"),
  mainGrid: $("main-grid"),
  colOuterLeft: $("col-outer-left"),
  btnLeftColToggle: $<HTMLButtonElement>("btn-leftcol-toggle"),
  lagebildTitle: $("lagebild-title"),
  btnLagebildToggle: $<HTMLButtonElement>("btn-lagebild-toggle"),
  terms: $("terms"),
  termStatus: $("term-status"),
  termCount: $("term-count"),
  feed: $("feed"),
  feedScroll: $("feed-scroll"),
  feedInfo: $("feed-info"),
  feedVariantToggle: $("feed-variant-toggle"),
  focusBar: $("focus-bar"),
  focusBarTerm: $("focus-bar-term"),
  focusBarCount: $("focus-bar-count"),
  focusBarClear: $<HTMLButtonElement>("focus-bar-clear"),
  focusWindowToggle: $("focus-window-toggle"),
  stats: $("stats"),
  toasts: $("toasts"),
};

// ---------------------------------------------------------------- Filter
const PLATFORMS = [
  ["all", "alle"],
  ["bluesky", "Bluesky"],
  ["reddit", "Reddit"],
  ["googlenews", "Google News"],
  ["news", "News"],
];
// Noch ohne Daten (keine aktiven Zugangsdaten) - hinter "Mehr" versteckt,
// statt leere Tabs in der Hauptleiste zu zeigen. Klick zeigt einen
// "demnächst verfügbar"-Hinweis statt tatsächlich zu filtern.
const MORE_PLATFORMS = [
  ["x", "X"],
  ["facebook", "Facebook"],
];
const CATEGORIES = [
  ["all", "alle themen"],
  ["cybersecurity", "cybersec"],
  ["it", "it"],
  ["nachrichten", "news"],
  ["alltag", "alltag"],
];

function renderTabs(): void {
  els.tabPlatform.innerHTML =
    PLATFORMS.map(
      ([v, l]) =>
        `<button class="tab ${state.filters.platform === v ? "active" : ""}" data-v="${v}">
       ${v !== "all" ? platformIcon(v, 12) : ""}<span>${l}</span>
       ${v !== "all" && state.stats?.by_platform[v] ? `<span class="cnt">${state.stats.by_platform[v]}</span>` : ""}
       </button>`,
    ).join("") +
    `<div class="tabs-more-anchor">
       <button class="tab tab-more" id="btn-more-platforms" type="button">
         <span>Mehr</span>
         <svg width="9" height="9" viewBox="0 0 12 12" fill="none" aria-hidden="true">
           <path d="M3 4 6 8l3-4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>
         </svg>
       </button>
       <div class="tabs-more-panel" id="more-platforms-panel" style="display:none">
         ${MORE_PLATFORMS.map(
           ([v, l]) => `<button class="tab" data-v="${v}">${platformIcon(v, 12)}<span>${l}</span></button>`,
         ).join("")}
       </div>
     </div>`;
  els.tabCategory.innerHTML = CATEGORIES.map(
    ([v, l]) => `<button class="tab ${state.filters.category === v ? "active" : ""}" data-v="${v}"><span>${l}</span></button>`,
  ).join("");

  els.tabPlatform.querySelectorAll<HTMLElement>(".tabs-more-panel .tab").forEach((b) =>
    b.addEventListener("click", (ev) => {
      ev.stopPropagation();
      toast(`${b.dataset.v === "x" ? "X" : "Facebook"}: demnächst verfügbar`);
      els.tabPlatform.querySelector<HTMLElement>("#more-platforms-panel")!.style.display = "none";
    }),
  );
  els.tabPlatform.querySelectorAll<HTMLElement>(":scope > .tab:not(.tab-more)").forEach((b) =>
    b.addEventListener("click", () => {
      state.filters.platform = b.dataset.v!;
      renderTabs();
      void reloadPosts();
    }),
  );
  els.tabPlatform.querySelector<HTMLButtonElement>("#btn-more-platforms")!.addEventListener("click", (ev) => {
    ev.stopPropagation();
    const panel = els.tabPlatform.querySelector<HTMLElement>("#more-platforms-panel")!;
    panel.style.display = panel.style.display === "none" ? "flex" : "none";
  });
  els.tabCategory.querySelectorAll<HTMLElement>(".tab").forEach((b) =>
    b.addEventListener("click", () => {
      state.filters.category = b.dataset.v!;
      renderTabs();
      void reloadPosts();
    }),
  );
}

document.addEventListener("click", (ev) => {
  const panel = document.getElementById("more-platforms-panel");
  const anchor = panel?.closest(".tabs-more-anchor");
  if (anchor && !anchor.contains(ev.target as Node)) panel!.style.display = "none";
});

function matchesFilter(p: Post): boolean {
  const f = state.filters;
  if (f.platform !== "all" && p.platform !== f.platform) return false;
  if (f.category !== "all" && !(p.categories || []).includes(f.category)) return false;
  if (f.minSeverity && p.severity < f.minSeverity) return false;
  // Bewusst per Freitext-Enthaltensein geprüft (wie f.query unten), nicht
  // über matched_terms: ein Beitrag, der schon vor dem Anlegen dieses Begriffs
  // existierte, wurde nie rückwirkend mit ihm getaggt, obwohl sein Text ihn
  // enthalten kann - matched_terms wäre hier also fälschlich leer.
  if (f.focusTerm) {
    const ft = f.focusTerm.toLowerCase();
    if (!`${p.title} ${p.text} ${p.author} ${p.source}`.toLowerCase().includes(ft)) return false;
    // Zeitfenster gilt nur im Fokus-Modus - blendet auf Wunsch alles vor
    // "jetzt"/"1h"/"24h" aus, damit man nach dem Fokussieren nicht durch bis
    // zu 200 gepufferte Treffer scrollen muss. Bewusst collected_at statt
    // created_at (wie die "vor Xm"-Anzeige in feed.ts): created_at ist die
    // Original-Zeit von der Quelle und kann bei RSS/Reddit deutlich älter
    // sein als der Zeitpunkt, zu dem wir den Beitrag tatsächlich eingesammelt
    // haben - sonst würde "Jetzt" gerade erst hereingekommene Treffer
    // rausfiltern, die im Feed als "vor 1m" angezeigt werden.
    if (f.focusWindowMinutes) {
      const ts = p.collected_at ? new Date(p.collected_at).getTime() : 0;
      if (Date.now() - ts > f.focusWindowMinutes * 60_000) return false;
    }
  }
  if (f.query) {
    const q = f.query.toLowerCase();
    if (!`${p.title} ${p.text} ${p.author} ${p.source}`.toLowerCase().includes(q)) return false;
  }
  return true;
}

function hasActiveFilter(): boolean {
  const f = state.filters;
  return f.platform !== "all" || f.category !== "all" || !!f.query || f.minSeverity > 0 || !!f.focusTerm;
}

function filterLabel(): string {
  const f = state.filters;
  const parts = [f.platform, f.category].filter((x) => x !== "all");
  if (f.focusTerm) parts.push(`#${f.focusTerm}`);
  if (f.query) parts.push(`"${f.query}"`);
  return parts.length ? parts.join(",") : "alle";
}

// -------------------------------------------------------------- Fokus-Modus
// Ein Klick auf einen Suchbegriff-Chip "zoomt" in dessen Treffer hinein:
// Feed, Quellen und Tag-Liste blenden alles aus, was nicht zu diesem einen
// Begriff gehört. Erneutes Klicken auf denselben Chip (oder das X in der
// Fokus-Leiste) hebt den Fokus wieder auf.
function setFocusTerm(term: string | null): void {
  state.filters.focusTerm = state.filters.focusTerm === term ? null : term;
  persistFocusTerm(state.filters.focusTerm);
  paintFeed();
  paintSources();
  paintTerms();
  paintHeader();
  if (state.filters.focusTerm) void hydrateFocusMatches(state.filters.focusTerm);
}

// Fokus-Modus filtert nur bereits geladene Beiträge (state.posts) - standard-
// mäßig aber nur die letzten ~150-400. Ein Tag mit vielen Treffern insgesamt
// (Chip zeigt z.B. "201") kann trotzdem "Kein Treffer" zeigen, wenn zufällig
// keiner der aktuell geladenen Beiträge darunter ist. Holt beim Aktivieren
// gezielt passende Beiträge nach - weiterhin nur ein rein lesender GET, wie
// von der Fokus-Modus-Spezifikation erlaubt.
async function hydrateFocusMatches(term: string): Promise<void> {
  try {
    const res = await api.posts({ q: term, limit: 200 });
    if (state.filters.focusTerm !== term) return; // Fokus zwischenzeitlich gewechselt/aufgehoben
    const known = new Set(state.posts.map((p) => p.id));
    const fresh = res.items.filter((p) => !known.has(p.id));
    if (!fresh.length) return;
    state.posts = [...state.posts, ...fresh].slice(0, MAX_BUFFER + 200);
    paintFeed();
    paintSources();
  } catch {
    /* stiller Fallback - Fokus bleibt auf den bereits geladenen Beiträgen beschränkt */
  }
}

// ---------------------------------------------------------------- Render
function paintFeed(): void {
  let visible = state.posts.filter(matchesFilter);
  if (state.resurfacedPostId != null) {
    const idx = visible.findIndex((p) => p.id === state.resurfacedPostId);
    if (idx > 0) {
      const [pinned] = visible.splice(idx, 1);
      visible = [pinned, ...visible];
    } else if (idx === -1) {
      state.resurfacedPostId = null;
    }
  }
  visible = visible.slice(0, 200);
  renderFeed(els.feed, visible, hasActiveFilter(), state.feedVariant);
  els.feedInfo.textContent = `${visible.length} sichtbar / ${state.posts.length} im Puffer`;

  const focus = state.filters.focusTerm;
  els.focusBar.style.display = focus ? "flex" : "none";
  if (focus) {
    els.focusBarTerm.textContent = `"${focus}"`;
    els.focusBarCount.textContent = ` · ${visible.length} Treffer`;
    els.focusWindowToggle.querySelectorAll<HTMLButtonElement>("button").forEach((b) => {
      b.classList.toggle("active", Number(b.dataset.min) === (state.filters.focusWindowMinutes ?? 0));
    });
  }
}

// ------------------------------------------------------- Rate-Limit-Fallback
// Wenn eine aktive Quelle gerade klemmt (harter Fehlerstatus ODER mehrere
// Läufe in Folge ohne einen einzigen neuen Beitrag - z.B. weil Reddit/Bluesky
// Anfragen stillschweigend mit 0 Treffern statt einem Fehler beantworten),
// wird alle 10s ein zufälliger, bereits geladener Beitrag von weiter unten im
// (gefilterten) Feed wieder nach oben geholt. Der echte Zeitstempel bleibt
// dabei erhalten - es wird nichts als "neu" vorgetäuscht. Sobald echte neue
// Beiträge kommen, verdrängen die sofort den wiederhochgeholten Beitrag.
//
// Hinweis: früher wurde hier nur der `detail`-Text auf "429"/"rate limit"
// geprüft - das griff aber nicht, weil (a) ein Backend-Block auch als 403
// oder als generischer CollectorError ankommen kann und (b) `detail` bei
// einem erfolgreichen, aber leeren Lauf (status "ok", items_last_run 0)
// gar nicht aktualisiert wird. Daher jetzt zusätzlich ein clientseitiger
// "leer Streak" pro Quelle.
function isRateLimited(): boolean {
  let stalled = false;
  for (const s of state.sources) {
    if (!s.enabled || s.status === "disabled") continue;
    if (s.status === "error" || s.consecutive_errors > 0) {
      state.stallStreak[s.name] = 0;
      stalled = true;
      continue;
    }
    const streak = s.items_last_run > 0 ? 0 : (state.stallStreak[s.name] ?? 0) + 1;
    state.stallStreak[s.name] = streak;
    if (streak >= 2) stalled = true;
  }
  return stalled;
}

function resurfaceOnce(): void {
  if (state.filters.paused) return;
  const visible = state.posts.filter(matchesFilter);
  if (visible.length < 4) return;
  const pool = visible.slice(3).filter((p) => p.id !== state.resurfacedPostId);
  if (!pool.length) return;
  state.resurfacedPostId = pool[Math.floor(Math.random() * pool.length)].id;
  paintFeed();
}

function updateResurfacing(): void {
  state.resurfaceActive = isRateLimited();
  if (!state.resurfaceActive && state.resurfacedPostId != null) {
    state.resurfacedPostId = null;
    paintFeed();
  }
}

// Wird bei jedem Takt-Ende aufgerufen (lokal oder per Server-"tick"-Event) -
// damit der Wechsel des wiederhochgeholten Beitrags exakt mit dem sichtbaren
// 10s-Countdown oben rechts zusammenfällt, statt auf einem eigenen,
// unabhängig laufenden (und irgendwann davondriftenden) Intervall zu hängen.
function onTickBoundary(): void {
  if (state.resurfaceActive) resurfaceOnce();
}

function paintHeader(): void {
  renderHeader(els.headerInner, {
    stats: state.stats,
    connected: state.connected,
    nextTick: state.nextTick,
    tickSeconds: state.tickSeconds,
    filterLabel: filterLabel(),
  });
  els.trGreen.classList.toggle("live", state.connected);
  els.trGreen.classList.toggle("pulse", state.connected);
}

function paintSources(): void {
  const focus = state.filters.focusTerm;
  const activePlatforms = focus
    ? new Set(
        state.posts
          .filter((p) => (p.matched_terms || []).includes(focus))
          .map((p) => p.platform),
      )
    : null;
  renderSources(
    els.sources,
    state.sources,
    activePlatforms,
    state.isAdmin,
    async (name, enabled) => {
      await api.patchSource(name, { enabled });
      toast(`${name}: ${enabled ? "aktiviert" : "deaktiviert"}`);
      state.sources = await api.sources();
      paintSources();
    },
    async (name) => {
      toast(`${name}: Sammellauf gestartet …`);
      try {
        const res = await api.collectNow(name);
        toast(`${name}: ${res.new} neue Beiträge`);
        await reloadPosts();
      } catch (e) {
        toast(String(e), true);
      }
      state.sources = await api.sources();
      paintSources();
    },
  );
  updateResurfacing();
}

function setTermStatus(text: string, kind: "busy" | "done" | "error" = "done"): void {
  els.termStatus.classList.toggle("done", kind === "done");
  els.termStatus.innerHTML = kind === "busy" ? `<span class="spin"></span> ${esc(text)}` : esc(text);
  window.clearTimeout((els.termStatus as any)._t);
  if (kind !== "busy") {
    (els.termStatus as any)._t = window.setTimeout(() => {
      els.termStatus.textContent = "";
      els.termStatus.classList.remove("done");
    }, 7000);
  }
}

function paintTerms(freshId?: number): void {
  els.termCount.textContent = `${state.terms.filter((t) => t.enabled).length}/${state.terms.length} aktiv`;
  renderTerms(
    els.terms,
    state.terms,
    {
      onAdd: async (term, category) => {
        setTermStatus(`„${term}“ wird angelegt und sofort gesucht …`, "busy");
        try {
          const created = await api.addTerm(term, category);
          state.terms = await api.terms();
          paintTerms(created.id);

          setTermStatus(`Suche „${term}“ läuft auf allen Quellen …`, "busy");
          const res = await api.collectNow();
          await reloadPosts();

          const found = (await api.posts({ limit: 1, q: term })).total;
          setTermStatus(
            `„${term}“ gespeichert · ${res.new} neue Beiträge aus ${res.ran.length} Quellen · ${found} Treffer insgesamt`,
            "done",
          );
        } catch (e) {
          setTermStatus(`Fehler beim Anlegen: ${e}`, "error");
          toast(String(e), true);
        }
      },
      onDelete: async (id) => {
        const deleted = state.terms.find((t) => t.id === id);
        await api.deleteTerm(id);
        state.terms = await api.terms();
        if (deleted && state.filters.focusTerm === deleted.term) setFocusTerm(null);
        paintTerms();
      },
      onToggle: async (id, enabled) => {
        await api.patchTerm(id, { enabled });
        state.terms = await api.terms();
        paintTerms();
      },
      onFocus: (term) => setFocusTerm(term),
    },
    state.filters.focusTerm,
    state.isAdmin,
    freshId,
  );
}

function toast(message: string, isError = false): void {
  const node = document.createElement("div");
  node.className = `toast ${isError ? "err" : ""}`;
  node.textContent = message;
  els.toasts.appendChild(node);
  setTimeout(() => node.remove(), 4200);
}

// ------------------------------------------------------------ Darstellung
function paintThemeIcon(): void {
  const isLight = state.settings.theme === "light";
  els.btnTheme.classList.toggle("light", isLight);
  els.btnTheme.setAttribute("aria-checked", String(isLight));
}

// Rein clientseitig (localStorage) statt PUT /api/settings: Theme ist eine
// persönliche Anzeige-Präferenz, kein geteilter Server-Zustand - ein Wechsel
// hier darf keine anderen Besucher betreffen und braucht daher keinen
// (jetzt Admin-geschützten) Schreibzugriff auf den Server.
async function toggleTheme(): Promise<void> {
  const theme = state.settings.theme === "light" ? "dark" : "light";
  state.settings = { ...state.settings, theme };
  applySettings(state.settings);
  paintThemeIcon();
  try {
    localStorage.setItem("netzwache.theme", theme);
  } catch {
    /* Storage nicht verfügbar - Wahl gilt dann nur für diese Sitzung */
  }
}

els.btnTheme.addEventListener("click", () => void toggleTheme());

els.focusBarClear.addEventListener("click", () => setFocusTerm(null));

els.focusWindowToggle.querySelectorAll<HTMLButtonElement>("button").forEach((b) => {
  b.addEventListener("click", () => {
    const minutes = Number(b.dataset.min) || null;
    if (minutes === state.filters.focusWindowMinutes) return;
    state.filters.focusWindowMinutes = minutes;
    persistFocusWindowMinutes(minutes);
    paintFeed();
  });
});

// -------------------------------------------------------------- Admin-Login
// Sichtbarkeit der Admin-Bedienelemente hängt allein von state.isAdmin ab,
// das wiederum nur durch eine erfolgreiche Server-Antwort gesetzt wird
// (/api/auth/me, /api/auth/login) - das Verstecken hier ist reine UX, die
// eigentliche Durchsetzung passiert serverseitig (Depends(require_admin)).
function applyAdminUi(): void {
  els.btnCollect.style.display = state.isAdmin ? "" : "none";
  els.btnAdmin.textContent = state.isAdmin ? "Logout" : "Admin";
  els.btnAdmin.title = state.isAdmin ? "Admin-Sitzung beenden" : "Admin-Anmeldung";
  els.adminLoginForm.style.display = "none";
  paintTerms();
  paintSources();
}

els.btnAdmin.addEventListener("click", () => {
  if (state.isAdmin) {
    void (async () => {
      await api.authLogout().catch(() => undefined);
      state.isAdmin = false;
      applyAdminUi();
      toast("Admin-Sitzung beendet");
    })();
    return;
  }
  const opening = els.adminLoginForm.style.display === "none";
  els.adminLoginForm.style.display = opening ? "flex" : "none";
  if (opening) els.adminUser.focus();
});

els.adminLoginForm.addEventListener("submit", (ev) => {
  ev.preventDefault();
  void (async () => {
    els.adminLoginErr.textContent = "";
    try {
      const res = await api.authLogin(els.adminUser.value, els.adminPass.value);
      state.isAdmin = res.authenticated;
      els.adminPass.value = "";
      applyAdminUi();
      toast("Als Admin angemeldet");
    } catch (e) {
      els.adminLoginErr.textContent = String(e);
    }
  })();
});

document.addEventListener("click", (ev) => {
  const t = ev.target as Node;
  const anchor = els.btnAdmin.closest(".admin-login-anchor");
  if (anchor && !anchor.contains(t)) els.adminLoginForm.style.display = "none";
});

// ------------------------------------------------------------ Datenfluss
async function reloadPosts(): Promise<void> {
  try {
    const res = await api.posts({
      limit: 150,
      platform: state.filters.platform,
      category: state.filters.category,
      q: state.filters.query,
      min_severity: state.filters.minSeverity,
    });
    state.posts = res.items;
    paintFeed();
  } catch (e) {
    toast(`Laden fehlgeschlagen: ${e}`, true);
  }
}

function prependPosts(incoming: Post[]): void {
  if (!incoming.length) return;
  const known = new Set(state.posts.map((p) => p.id));
  const fresh = incoming.filter((p) => !known.has(p.id));
  if (!fresh.length) return;

  state.posts = [...fresh.reverse(), ...state.posts].slice(0, MAX_BUFFER);

  if (state.filters.paused) return;

  const visible = fresh.filter(matchesFilter);
  if (!visible.length) {
    els.feedInfo.textContent = `${els.feed.children.length} sichtbar / ${state.posts.length} im Puffer`;
    return;
  }
  if (state.resurfacedPostId != null) {
    // Echte neue Beiträge verdrängen sofort den wiederhochgeholten Beitrag.
    state.resurfacedPostId = null;
    paintFeed();
    return;
  }
  if (state.feedVariant === "grid") {
    paintFeed();
    return;
  }
  const atTop = els.feedScroll.scrollTop < 60;
  els.feed.insertAdjacentHTML("afterbegin", visible.map((p) => postCard(p, true)).join(""));
  while (els.feed.children.length > 200) els.feed.lastElementChild?.remove();
  attachExpand(els.feed);
  if (atTop) els.feedScroll.scrollTop = 0;
  els.feedInfo.textContent = `${els.feed.children.length} sichtbar / ${state.posts.length} im Puffer`;
}

async function refreshStats(): Promise<void> {
  try {
    const stats = await api.stats();
    state.stats = stats;
    renderStats(els.stats, state.stats);
    renderTabs();
    paintHeader();
  } catch {
    /* Backend noch nicht bereit */
  }
}

// ---------------------------------------------------------------- Events
restrictToAlnum(els.search);
els.search.addEventListener("input", () => {
  state.filters.query = els.search.value.trim();
  paintHeader();
  clearTimeout((els.search as any)._t);
  (els.search as any)._t = setTimeout(() => void reloadPosts(), 320);
});

els.btnSourcesToggle.addEventListener("click", () => {
  state.sourcesOpen = !state.sourcesOpen;
  els.sources.classList.toggle("collapsed", !state.sourcesOpen);
  els.btnSourcesToggle.classList.toggle("open", state.sourcesOpen);
});

els.btnLeftColToggle.addEventListener("click", () => {
  state.leftColOpen = !state.leftColOpen;
  els.colOuterLeft.classList.toggle("collapsed", !state.leftColOpen);
  els.btnLeftColToggle.classList.toggle("flip", !state.leftColOpen);
  els.mainGrid.classList.toggle("left-collapsed", !state.leftColOpen);
});

els.btnLagebildToggle.addEventListener("click", () => {
  state.lagebildOpen = !state.lagebildOpen;
  els.lagebildTitle.style.display = state.lagebildOpen ? "" : "none";
  els.stats.classList.toggle("collapsed", !state.lagebildOpen);
  els.btnLagebildToggle.classList.toggle("flip", state.lagebildOpen);
  els.mainGrid.classList.toggle("right-collapsed", !state.lagebildOpen);
});

els.feedVariantToggle.querySelectorAll<HTMLButtonElement>("button").forEach((b) => {
  b.addEventListener("click", () => {
    const variant = b.dataset.v as FeedVariant;
    if (variant === state.feedVariant) return;
    state.feedVariant = variant;
    els.feedVariantToggle.querySelectorAll("button").forEach((x) => x.classList.remove("active"));
    b.classList.add("active");
    paintFeed();
  });
});

els.btnPause.addEventListener("click", togglePause);

function togglePause(): void {
  state.filters.paused = !state.filters.paused;
  els.btnPause.textContent = state.filters.paused ? "▶ Weiter" : "⏸ Pause";
  els.btnPause.classList.toggle("btn-go", state.filters.paused);
  toast(state.filters.paused ? "Live-Stream angehalten" : "Live-Stream läuft");
  if (!state.filters.paused) paintFeed();
}

els.btnCollect.addEventListener("click", async () => {
  els.btnCollect.disabled = true;
  els.btnCollect.textContent = "… sammelt";
  try {
    const res = await api.collectNow();
    toast(`${res.ran.length} Quellen abgefragt · ${res.new} neue Beiträge`);
    await reloadPosts();
  } catch (e) {
    toast(String(e), true);
  } finally {
    els.btnCollect.disabled = false;
    els.btnCollect.textContent = "▶ Jetzt sammeln";
  }
});

document.addEventListener("keydown", (ev) => {
  if (ev.target instanceof HTMLInputElement || ev.target instanceof HTMLSelectElement) return;
  if (ev.code === "Space") {
    ev.preventDefault();
    togglePause();
  }
  if (ev.key === "/") {
    ev.preventDefault();
    els.search.focus();
  }
  if (ev.key === "Escape" && state.filters.focusTerm) {
    setFocusTerm(null);
  }
});

// ------------------------------------------------------------ WebSocket
const stream = new LiveStream((event, data) => {
  switch (event) {
    case "__status":
      state.connected = data.connected;
      paintHeader();
      break;
    case "snapshot":
      state.tickSeconds = data.tick_seconds ?? 10;
      state.nextTick = state.tickSeconds;
      state.posts = (data.posts as Post[]).slice().reverse();
      state.sources = data.sources;
      paintFeed();
      paintSources();
      // Fokus kann aus sessionStorage stammen (Reload im selben Tab) - die
      // Snapshot-Beiträge allein enthalten dann oft nicht genug Treffer,
      // siehe hydrateFocusMatches().
      if (state.filters.focusTerm) void hydrateFocusMatches(state.filters.focusTerm);
      break;
    case "posts":
      prependPosts(data as Post[]);
      break;
    case "sources":
      state.sources = data;
      paintSources();
      break;
    case "settings":
      // Änderung auf einem anderen Gerät -> hier ebenfalls übernehmen
      state.settings = data as UiSettings;
      applySettings(state.settings);
      paintThemeIcon();
      break;
    case "tick":
      state.nextTick = state.tickSeconds;
      onTickBoundary();
      paintHeader();
      break;
  }
});

// ---------------------------------------------------------------- Bootup
async function boot(): Promise<void> {
  renderTabs();
  paintHeader();

  try {
    const health: any = await api.health();
    state.tickSeconds = Number(health.tick_seconds ?? 10);
    state.nextTick = state.tickSeconds;
  } catch {
    toast("Backend nicht erreichbar – läuft es auf Port 8000?", true);
  }

  const [sources, terms, settings, auth] = await Promise.all([
    api.sources().catch(() => []),
    api.terms().catch(() => []),
    api.settings().catch(() => DEFAULT_SETTINGS),
    api.authMe().catch(() => ({ authenticated: false })),
  ]);
  state.sources = sources;
  state.terms = terms;
  state.settings = settings;
  state.isAdmin = auth.authenticated;
  // Eigene, zuvor lokal gespeicherte Theme-Wahl geht vor dem Server-Standard -
  // siehe toggleTheme(): Theme wird nicht mehr per PUT /api/settings geschrieben.
  try {
    const storedTheme = localStorage.getItem("netzwache.theme");
    if (storedTheme === "light" || storedTheme === "dark") {
      state.settings = { ...state.settings, theme: storedTheme };
    }
  } catch {
    /* Storage nicht verfügbar - Server-Standard bleibt bestehen */
  }
  applySettings(state.settings);
  paintThemeIcon();
  applyAdminUi();

  await reloadPosts();
  await refreshStats();

  stream.connect();

  // Sekundentakt: Uhr + Countdown
  // Läuft lokal von allein weiter und springt bei 0 selbst wieder auf
  // tickSeconds zurück - verlässt sich nicht mehr allein auf das "tick"-
  // WS-Event vom Server. Blieb sonst dauerhaft bei 0 stehen, wenn genau
  // dieses eine Event verloren ging oder der Server-Takt sich verzögerte
  // (z.B. durch einen langsamen Collector-Lauf). Das echte "tick"-Event
  // gleicht die Anzeige weiterhin mit dem Server ab, sobald es eintrifft.
  setInterval(() => {
    if (state.nextTick > 0) {
      state.nextTick -= 1;
    } else {
      state.nextTick = state.tickSeconds;
      onTickBoundary();
    }
    paintHeader();
  }, 1000);

  // Kennzahlen alle 10 s nachziehen
  setInterval(() => void refreshStats(), 10_000);

  // Relative Zeitangaben aktuell halten
  setInterval(() => {
    if (!state.filters.paused) paintFeed();
  }, 60_000);
}

void boot();

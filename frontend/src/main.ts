import "./styles.css";

import { api } from "./api";
import { renderDiagnosticsPanel } from "./components/diagnosticsPanel";
import { attachExpand, postCard, renderFeed, squareCard, type FeedVariant } from "./components/feed";
import { renderHeader } from "./components/header";
import { applySettings, renderSettingsPanel } from "./components/settingsPanel";
import { renderSources } from "./components/sources";
import { renderStats } from "./components/stats";
import { renderTerms } from "./components/terms";
import { platformIcon } from "./icons";
import type { Diagnostics, Filters, Post, SourceState, Stats, Term, UiSettings } from "./types";
import { esc } from "./utils";
import { LiveStream } from "./ws";

const MAX_BUFFER = 400;

const DEFAULT_SETTINGS: UiSettings = {
  font_family: "jetbrains",
  font_size: "13",
  density: "comfortable",
  theme: "macos-linux",
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
  diagnostics: null as Diagnostics | null,
  sourcesOpen: true,
  leftColOpen: true,
  lagebildOpen: true,
  feedVariant: "list" as FeedVariant,
  filters: {
    platform: "all",
    category: "all",
    query: "",
    minSeverity: 0,
    paused: false,
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

    <div class="popover-anchor">
      <button id="btn-display" class="icon-btn" title="Darstellung: Schriftart, Größe, Dichte">Aa</button>
      <div class="popover" id="pop-display" style="display:none"></div>
    </div>
    <div class="popover-anchor">
      <button id="btn-diag" class="icon-btn" title="Diagnose">⚕</button>
      <div class="popover wide" id="pop-diag" style="display:none"></div>
    </div>
  </div>

  <div class="main" id="main-grid">
    <div class="col col-left">
      <div class="col-outer" id="col-outer-left">
        <div class="col-outer-head">
          <span class="panel-title" id="left-outer-title">Suchraum</span>
          <button id="btn-leftcol-toggle" class="icon-btn collapse-toggle" title="Suchraum ein-/ausblenden">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
              <path d="M8.5 3.5 4.5 7l4 3.5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>
              <path d="M12 3.5 8 7l4 3.5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>
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
              <button id="btn-sources-toggle" class="icon-btn lg chevron open" title="Quellen ein-/ausblenden">
                <svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true">
                  <path d="M3 4.5 6 8l3-3.5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
              </button>
            </div>
            <div class="panel-body tight" id="sources"></div>
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
        <div class="panel-body tight" id="feed-scroll">
          <div class="feed" id="feed"></div>
        </div>
      </section>
    </div>

    <div class="col col-right">
      <section class="panel" style="flex:1 1 auto">
        <div class="panel-head">
          <span class="panel-title" id="lagebild-title">Lagebild</span>
          <button id="btn-lagebild-toggle" class="icon-btn collapse-toggle flip" title="Lagebild ein-/ausblenden">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
              <path d="M8.5 3.5 4.5 7l4 3.5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>
              <path d="M12 3.5 8 7l4 3.5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
          </button>
        </div>
        <div class="panel-body" id="stats"></div>
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
  btnDisplay: $<HTMLButtonElement>("btn-display"),
  popDisplay: $("pop-display"),
  btnDiag: $<HTMLButtonElement>("btn-diag"),
  popDiag: $("pop-diag"),
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
  stats: $("stats"),
  toasts: $("toasts"),
};

// ---------------------------------------------------------------- Filter
const PLATFORMS = [
  ["all", "alle"],
  ["bluesky", "Bluesky"],
  ["reddit", "Reddit"],
  ["x", "X"],
  ["facebook", "Facebook"],
  ["news", "News"],
];
const CATEGORIES = [
  ["all", "alle themen"],
  ["cybersecurity", "cybersec"],
  ["it", "it"],
  ["nachrichten", "news"],
  ["alltag", "alltag"],
];

function renderTabs(): void {
  els.tabPlatform.innerHTML = PLATFORMS.map(
    ([v, l]) =>
      `<button class="tab ${state.filters.platform === v ? "active" : ""}" data-v="${v}">
       ${v !== "all" ? platformIcon(v, 12) : ""}<span>${l}</span>
       ${v !== "all" && state.stats?.by_platform[v] ? `<span class="cnt">${state.stats.by_platform[v]}</span>` : ""}
       </button>`,
  ).join("");
  els.tabCategory.innerHTML = CATEGORIES.map(
    ([v, l]) => `<button class="tab ${state.filters.category === v ? "active" : ""}" data-v="${v}"><span>${l}</span></button>`,
  ).join("");

  els.tabPlatform.querySelectorAll<HTMLElement>(".tab").forEach((b) =>
    b.addEventListener("click", () => {
      state.filters.platform = b.dataset.v!;
      renderTabs();
      void reloadPosts();
    }),
  );
  els.tabCategory.querySelectorAll<HTMLElement>(".tab").forEach((b) =>
    b.addEventListener("click", () => {
      state.filters.category = b.dataset.v!;
      renderTabs();
      void reloadPosts();
    }),
  );
}

function matchesFilter(p: Post): boolean {
  const f = state.filters;
  if (f.platform !== "all" && p.platform !== f.platform) return false;
  if (f.category !== "all" && !(p.categories || []).includes(f.category)) return false;
  if (f.minSeverity && p.severity < f.minSeverity) return false;
  if (f.query) {
    const q = f.query.toLowerCase();
    if (!`${p.title} ${p.text} ${p.author} ${p.source}`.toLowerCase().includes(q)) return false;
  }
  return true;
}

function hasActiveFilter(): boolean {
  const f = state.filters;
  return f.platform !== "all" || f.category !== "all" || !!f.query || f.minSeverity > 0;
}

function filterLabel(): string {
  const f = state.filters;
  const parts = [f.platform, f.category].filter((x) => x !== "all");
  if (f.query) parts.push(`"${f.query}"`);
  return parts.length ? parts.join(",") : "alle";
}

// ---------------------------------------------------------------- Render
function paintFeed(): void {
  const visible = state.posts.filter(matchesFilter).slice(0, 200);
  renderFeed(els.feed, visible, hasActiveFilter(), state.feedVariant);
  els.feedInfo.textContent = `${visible.length} sichtbar / ${state.posts.length} im Puffer`;
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
  renderSources(
    els.sources,
    state.sources,
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
        await api.deleteTerm(id);
        state.terms = await api.terms();
        paintTerms();
      },
      onToggle: async (id, enabled) => {
        await api.patchTerm(id, { enabled });
        state.terms = await api.terms();
        paintTerms();
      },
    },
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
function paintDisplayPanel(): void {
  renderSettingsPanel(els.popDisplay, state.settings, async (patch) => {
    state.settings = { ...state.settings, ...patch };
    try {
      state.settings = await api.putSettings(patch);
    } catch (e) {
      toast(`Einstellung nicht gespeichert: ${e}`, true);
    }
  });
}

function paintDiagPanel(): void {
  renderDiagnosticsPanel(els.popDiag, state.diagnostics);
}

function closePopovers(except?: HTMLElement): void {
  for (const p of [els.popDisplay, els.popDiag]) {
    if (p !== except) p.style.display = "none";
  }
  els.btnDisplay.classList.toggle("active", els.popDisplay.style.display !== "none");
  els.btnDiag.classList.toggle("active", els.popDiag.style.display !== "none");
}

els.btnDisplay.addEventListener("click", (ev) => {
  ev.stopPropagation();
  const opening = els.popDisplay.style.display === "none";
  closePopovers();
  if (opening) {
    els.popDisplay.style.display = "block";
    els.btnDisplay.classList.add("active");
    paintDisplayPanel();
  }
});

els.btnDiag.addEventListener("click", (ev) => {
  ev.stopPropagation();
  const opening = els.popDiag.style.display === "none";
  closePopovers();
  if (opening) {
    els.popDiag.style.display = "block";
    els.btnDiag.classList.add("active");
    paintDiagPanel();
    void api
      .diagnostics()
      .then((d) => {
        state.diagnostics = d;
        paintDiagPanel();
      })
      .catch((e) => toast(String(e), true));
  }
});

document.addEventListener("click", (ev) => {
  const t = ev.target as Node;
  if (!els.popDisplay.contains(t) && !els.popDiag.contains(t)) closePopovers();
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
  if (ev.key === "Escape") closePopovers();
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
      if (els.popDisplay.style.display !== "none") paintDisplayPanel();
      break;
    case "tick":
      state.nextTick = state.tickSeconds;
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

  const [sources, terms, settings] = await Promise.all([
    api.sources().catch(() => []),
    api.terms().catch(() => []),
    api.settings().catch(() => DEFAULT_SETTINGS),
  ]);
  state.sources = sources;
  state.terms = terms;
  state.settings = settings;
  applySettings(state.settings);
  paintSources();
  paintTerms();

  await reloadPosts();
  await refreshStats();

  stream.connect();

  // Sekundentakt: Uhr + Countdown
  setInterval(() => {
    state.nextTick = Math.max(0, state.nextTick - 1);
    paintHeader();
  }, 1000);

  // Kennzahlen alle 10 s nachziehen
  setInterval(() => void refreshStats(), 10_000);

  // Relative Zeitangaben aktuell halten
  setInterval(() => {
    if (!state.filters.paused) paintFeed();
  }, 60_000);

  // Diagnose-Panel bei Bedarf frisch halten, solange geöffnet
  setInterval(() => {
    if (els.popDiag.style.display !== "none") {
      void api
        .diagnostics()
        .then((d) => {
          state.diagnostics = d;
          paintDiagPanel();
        })
        .catch(() => {});
    }
  }, 15_000);
}

void boot();

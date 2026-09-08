import { api } from "../api";
import type { StorageInfo } from "../types";
import { esc } from "../utils";

/** Kleiner, wiederverwendbarer Bestätigungsdialog - für "wirklich ändern?"
 * genauso wie für die schärfere Löschbestätigung mit Bestätigungswort.
 * Eigenes Overlay statt window.confirm(), damit es zum Rest der Oberfläche passt. */
export function showConfirmModal(opts: {
  title: string;
  message: string;
  confirmLabel: string;
  danger?: boolean;
  requirePhrase?: string; // wenn gesetzt: Bestätigen erst aktiv, wenn exakt eingetippt
  onConfirm: () => void | Promise<void>;
  onError?: (message: string) => void;
}): void {
  const overlay = document.createElement("div");
  overlay.className = "modal-overlay";
  overlay.innerHTML = `
    <div class="modal-panel modal-panel-sm">
      <div class="modal-head"><span class="panel-title">${esc(opts.title)}</span></div>
      <div class="modal-body">
        <p class="confirm-message">${esc(opts.message)}</p>
        ${
          opts.requirePhrase
            ? `<input type="text" class="confirm-phrase-input" placeholder="${esc(opts.requirePhrase)}" autocomplete="off" spellcheck="false" />`
            : ""
        }
        <div class="modal-actions">
          <button type="button" class="btn-ghost" data-act="cancel">Abbrechen</button>
          <button type="button" class="${opts.danger ? "btn-danger" : "btn-go"}" data-act="confirm"${
            opts.requirePhrase ? " disabled" : ""
          }>${esc(opts.confirmLabel)}</button>
        </div>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);

  const yesBtn = overlay.querySelector<HTMLButtonElement>('[data-act="confirm"]')!;
  const cancelBtn = overlay.querySelector<HTMLButtonElement>('[data-act="cancel"]')!;
  const phraseInput = overlay.querySelector<HTMLInputElement>(".confirm-phrase-input");

  const close = () => overlay.remove();
  const onKeydown = (ev: KeyboardEvent) => {
    if (ev.key === "Escape") close();
  };
  document.addEventListener("keydown", onKeydown, { once: true });

  if (phraseInput) {
    phraseInput.addEventListener("input", () => {
      yesBtn.disabled = phraseInput.value !== opts.requirePhrase;
    });
    phraseInput.focus();
  }

  cancelBtn.addEventListener("click", close);
  overlay.addEventListener("click", (ev) => {
    if (ev.target === overlay) close();
  });

  yesBtn.addEventListener("click", () => {
    void (async () => {
      yesBtn.disabled = true;
      const original = yesBtn.textContent;
      yesBtn.textContent = "…";
      try {
        await opts.onConfirm();
        close();
      } catch (e) {
        yesBtn.disabled = phraseInput ? phraseInput.value !== opts.requirePhrase : false;
        yesBtn.textContent = original;
        opts.onError?.(String(e));
      }
    })();
  });
}

function fmtBytes(bytes: number): string {
  const gb = bytes / 1024 ** 3;
  return gb >= 1 ? `${gb.toFixed(2)} GB` : `${(bytes / 1024 ** 2).toFixed(0)} MB`;
}

let modalEl: HTMLDivElement | null = null;

function closeStoragePanel(): void {
  modalEl?.remove();
  modalEl = null;
}

/** Öffnet die Speicherverwaltung (Admin) - lädt den aktuellen Stand frisch
 * bei jedem Öffnen, damit die Anzeige nie veraltet ist. */
export function openStoragePanel(onPostsCleared: () => void, onToast: (msg: string, isError?: boolean) => void): void {
  closeStoragePanel();

  const overlay = document.createElement("div");
  overlay.className = "modal-overlay";
  overlay.innerHTML = `
    <div class="modal-panel">
      <div class="modal-head">
        <span class="panel-title">Speicherverwaltung</span>
        <button type="button" class="icon-btn" data-act="close" title="Schließen">✕</button>
      </div>
      <div class="modal-body" id="storage-body">
        <div class="empty">Lädt …</div>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);
  modalEl = overlay;

  overlay.querySelector('[data-act="close"]')!.addEventListener("click", closeStoragePanel);
  overlay.addEventListener("click", (ev) => {
    if (ev.target === overlay) closeStoragePanel();
  });

  void loadAndRender(onPostsCleared, onToast);
}

async function loadAndRender(
  onPostsCleared: () => void,
  onToast: (msg: string, isError?: boolean) => void,
): Promise<void> {
  const body = modalEl?.querySelector<HTMLDivElement>("#storage-body");
  if (!body) return;

  let info: StorageInfo;
  try {
    info = await api.storageInfo();
  } catch (e) {
    body.innerHTML = `<div class="empty">Laden fehlgeschlagen: ${esc(String(e))}</div>`;
    return;
  }
  if (!modalEl) return; // zwischenzeitlich geschlossen

  const usedBytes = info.current_size_bytes ?? 0;
  const limitBytes = info.max_posts_size_gb * 1024 ** 3;
  const pct = info.size_tracking_available && limitBytes ? Math.min(100, (usedBytes / limitBytes) * 100) : 0;
  const warn = pct >= 90;

  body.innerHTML = `
    ${
      info.size_tracking_available
        ? `
    <div>
      <div class="storage-bar"><div class="storage-bar-fill${warn ? " warn" : ""}" style="width:${pct.toFixed(1)}%"></div></div>
      <div class="storage-usage-text">${esc(fmtBytes(usedBytes))} von ${info.max_posts_size_gb.toFixed(0)} GB belegt &middot; ${info.post_count.toLocaleString("de-DE")} Beiträge</div>
    </div>`
        : `<div class="storage-usage-text">Live-Größenanzeige nur unter Postgres verfügbar (aktuell SQLite) &middot; ${info.post_count.toLocaleString("de-DE")} Beiträge</div>`
    }

    <div class="storage-field">
      <label for="storage-max-gb">Speicherlimit <b id="storage-max-gb-val">${info.max_posts_size_gb.toFixed(0)} GB</b></label>
      <div class="storage-field-row">
        <input type="range" id="storage-max-gb" min="${info.min_size_gb}" max="${info.max_size_gb}" step="1" value="${info.max_posts_size_gb}" style="flex:1" />
        <button type="button" class="btn-go" id="storage-max-gb-apply">Übernehmen</button>
      </div>
    </div>

    <div class="storage-field">
      <label for="storage-chunk-mb">Löschmenge pro Räumung <b id="storage-chunk-mb-val">${info.posts_trim_chunk_mb.toFixed(0)} MB</b></label>
      <div class="storage-field-row">
        <input type="range" id="storage-chunk-mb" min="${info.min_chunk_mb}" max="${info.max_chunk_mb}" step="10" value="${info.posts_trim_chunk_mb}" style="flex:1" />
        <button type="button" class="btn-go" id="storage-chunk-mb-apply">Übernehmen</button>
      </div>
    </div>

    <div class="danger-zone">
      <p>Löscht <b>alle</b> gesammelten Beiträge unwiderruflich (Kategorien-/Tag-/CVE-Zuordnungen fallen automatisch mit weg). Suchbegriffe, Quellen und Einstellungen bleiben erhalten - die Sammlung läuft direkt danach weiter.</p>
      <button type="button" class="btn-danger" id="storage-delete-all">Alle Beiträge löschen</button>
    </div>
  `;

  const maxGbInput = body.querySelector<HTMLInputElement>("#storage-max-gb")!;
  const maxGbVal = body.querySelector<HTMLSpanElement>("#storage-max-gb-val")!;
  maxGbInput.addEventListener("input", () => {
    maxGbVal.textContent = `${Number(maxGbInput.value).toFixed(0)} GB`;
  });
  body.querySelector("#storage-max-gb-apply")!.addEventListener("click", () => {
    const value = Number(maxGbInput.value);
    showConfirmModal({
      title: "Speicherlimit ändern",
      message: `Speicherlimit auf ${value.toFixed(0)} GB setzen? Wird es gesenkt, räumt das System das in kleinen Schritten über die nächsten Sammel-Läufe nach, nicht sofort.`,
      confirmLabel: "Übernehmen",
      onConfirm: async () => {
        await api.putSettings({ max_posts_size_gb: String(value) });
        onToast(`Speicherlimit auf ${value.toFixed(0)} GB gesetzt`);
        await loadAndRender(onPostsCleared, onToast);
      },
      onError: (msg) => onToast(msg, true),
    });
  });

  const chunkInput = body.querySelector<HTMLInputElement>("#storage-chunk-mb")!;
  const chunkVal = body.querySelector<HTMLSpanElement>("#storage-chunk-mb-val")!;
  chunkInput.addEventListener("input", () => {
    chunkVal.textContent = `${Number(chunkInput.value).toFixed(0)} MB`;
  });
  body.querySelector("#storage-chunk-mb-apply")!.addEventListener("click", () => {
    const value = Number(chunkInput.value);
    showConfirmModal({
      title: "Löschmenge ändern",
      message: `Pro Räumung künftig ~${value.toFixed(0)} MB der ältesten Beiträge löschen, sobald das Speicherlimit erreicht ist?`,
      confirmLabel: "Übernehmen",
      onConfirm: async () => {
        await api.putSettings({ posts_trim_chunk_mb: String(value) });
        onToast(`Löschmenge auf ${value.toFixed(0)} MB gesetzt`);
        await loadAndRender(onPostsCleared, onToast);
      },
      onError: (msg) => onToast(msg, true),
    });
  });

  body.querySelector("#storage-delete-all")!.addEventListener("click", () => {
    showConfirmModal({
      title: "Alle Beiträge löschen",
      message: `Das entfernt unwiderruflich alle ${info.post_count.toLocaleString("de-DE")} gesammelten Beiträge. Zum Bestätigen "LÖSCHEN" eintippen.`,
      confirmLabel: "Endgültig löschen",
      danger: true,
      requirePhrase: "LÖSCHEN",
      onConfirm: async () => {
        const res = await api.deleteAllPosts("LÖSCHEN");
        onToast(`${res.removed} Beiträge gelöscht`);
        onPostsCleared();
        closeStoragePanel();
      },
      onError: (msg) => onToast(msg, true),
    });
  });
}

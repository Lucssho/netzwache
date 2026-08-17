import type { Density, FontKey, UiSettings } from "../types";

const FONTS: [FontKey, string][] = [
  ["jetbrains", "JetBrains Mono"],
  ["fira", "Fira Code"],
  ["sfmono", "SF Mono (macOS)"],
  ["menlo", "Menlo"],
  ["consolas", "Consolas"],
  ["inter", "Inter (serifenlos)"],
  ["system", "Systemschrift"],
];

const DENSITIES: [Density, string][] = [
  ["compact", "kompakt"],
  ["comfortable", "normal"],
  ["relaxed", "luftig"],
];

/** Wendet Schriftart/-größe/Dichte sofort auf das Dokument an (manuelle Umschaltung). */
export function applySettings(s: UiSettings): void {
  const html = document.documentElement;
  html.dataset.font = s.font_family;
  html.dataset.density = s.density;
  html.style.setProperty("--ui-font-size", `${s.font_size}px`);
}

export function renderSettingsPanel(
  el: HTMLElement,
  current: UiSettings,
  onChange: (patch: Record<string, string>) => void,
): void {
  el.innerHTML = `
    <h4>Darstellung</h4>

    <div class="row">
      <label for="opt-font">Schriftart (gilt für die ganze Oberfläche)</label>
      <select id="opt-font">
        ${FONTS.map(([k, l]) => `<option value="${k}" ${k === current.font_family ? "selected" : ""}>${l}</option>`).join("")}
      </select>
    </div>

    <div class="row">
      <label for="opt-size">Schriftgröße: <span id="opt-size-val">${current.font_size}px</span></label>
      <input type="range" id="opt-size" min="11" max="18" step="1" value="${current.font_size}" />
    </div>

    <div class="row">
      <label>Dichte</label>
      <div class="seg" id="opt-density">
        ${DENSITIES.map(
          ([k, l]) => `<button type="button" data-v="${k}" class="${k === current.density ? "active" : ""}">${l}</button>`,
        ).join("")}
      </div>
    </div>
  `;

  const fontSel = el.querySelector<HTMLSelectElement>("#opt-font")!;
  const sizeInput = el.querySelector<HTMLInputElement>("#opt-size")!;
  const sizeVal = el.querySelector<HTMLElement>("#opt-size-val")!;
  const densityBox = el.querySelector<HTMLElement>("#opt-density")!;

  fontSel.addEventListener("change", () => {
    const font_family = fontSel.value as FontKey;
    document.documentElement.dataset.font = font_family;
    onChange({ font_family });
  });

  sizeInput.addEventListener("input", () => {
    sizeVal.textContent = `${sizeInput.value}px`;
    document.documentElement.style.setProperty("--ui-font-size", `${sizeInput.value}px`);
  });
  sizeInput.addEventListener("change", () => onChange({ font_size: sizeInput.value }));

  densityBox.querySelectorAll<HTMLButtonElement>("button").forEach((b) => {
    b.addEventListener("click", () => {
      densityBox.querySelectorAll("button").forEach((x) => x.classList.remove("active"));
      b.classList.add("active");
      const density = b.dataset.v as Density;
      document.documentElement.dataset.density = density;
      onChange({ density });
    });
  });
}

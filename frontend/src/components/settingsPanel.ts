import type { UiSettings } from "../types";

/** Wendet Schriftart/-größe/Dichte/Theme sofort auf das Dokument an (manuelle Umschaltung). */
export function applySettings(s: UiSettings): void {
  const html = document.documentElement;
  html.dataset.font = s.font_family;
  html.dataset.density = s.density;
  html.dataset.theme = s.theme === "light" ? "light" : "dark";
  html.style.setProperty("--ui-font-size", `${s.font_size}px`);
}

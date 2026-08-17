export function esc(s: string): string {
  return (s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c] as string,
  );
}

export function relTime(iso: string | null): string {
  if (!iso) return "--";
  const d = new Date(iso).getTime();
  if (Number.isNaN(d)) return "--";
  const s = Math.max(0, Math.floor((Date.now() - d) / 1000));
  if (s < 10) return "gerade eben";
  if (s < 60) return `vor ${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `vor ${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return `vor ${h}h`;
  const t = Math.floor(h / 24);
  return `vor ${t}d`;
}

export function clock(): string {
  return new Date().toLocaleTimeString("de-DE", { hour12: false });
}

export function uptime(seconds: number): string {
  const s = Math.floor(seconds);
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (d) return `${d}d ${h}h ${m}m`;
  if (h) return `${h}h ${m}m ${sec}s`;
  return `${m}m ${sec}s`;
}

export function num(n: number): string {
  return n.toLocaleString("de-DE");
}

/** Hebt Suchbegriffe im Text hervor (nach dem Escapen!). */
export function highlight(escaped: string, terms: string[]): string {
  if (!terms.length) return escaped;
  const safe = terms
    .filter((t) => t.length > 2)
    .map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  if (!safe.length) return escaped;
  return escaped.replace(new RegExp(`(${safe.join("|")})`, "gi"), "<mark>$1</mark>");
}

export function severityClass(v: number): string {
  if (v >= 60) return "high";
  if (v >= 30) return "mid";
  return "";
}

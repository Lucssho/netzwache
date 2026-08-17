/**
 * Plattform-Symbole als Inline-SVG (echte Markenzeichen, keine Text-Badges).
 * Eine Funktion je Plattform, alle im selben Format: currentColor-Strich,
 * damit sie sich per CSS einfärben lassen und in jeder Fußzeile identisch
 * wirken.
 */

type IconFn = (size?: number) => string;

const wrap = (size: number, body: string, viewBox = "0 0 24 24") =>
  `<svg width="${size}" height="${size}" viewBox="${viewBox}" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">${body}</svg>`;

/** X (vormals Twitter) - das aktuelle "X"-Wortzeichen. */
const x: IconFn = (size = 14) =>
  wrap(
    size,
    `<path d="M13.9 10.4 21.4 2h-1.8l-6.5 7.3L7.9 2H2l7.9 11.2L2 22h1.8l6.9-7.7 5.5 7.7H22l-8.1-11.6Zm-2.4 2.8-.8-1.1L4.3 3.3h2.7l5.1 7.2.8 1.1 6.7 9.4h-2.7l-5.4-7.6Z" fill="currentColor"/>`,
  );

/** Bluesky - der Schmetterling. */
const bluesky: IconFn = (size = 14) =>
  wrap(
    size,
    `<path d="M12 8.4C10.6 5.7 7.8 3.4 5.4 2.4 3.4 1.6 2.5 2 3 4.1c.4 1.9 1.2 6.1 1.7 7.6.7 2.3 3.2 3 5.3 2.6-3.4.5-6.5 1.9-2.4 6.2 4.4 4.6 6-1 6.4-2.3.4 1.3 2 6.9 6.4 2.3 3.9-4.1.9-5.7-2.5-6.2 2.1.4 4.6-.3 5.3-2.6.5-1.5 1.3-5.7 1.7-7.6.5-2.1-.4-2.5-2.4-1.7C16.2 3.4 13.4 5.7 12 8.4Z" fill="currentColor"/>`,
  );

/** Reddit - das Alien-Maskottchen (vereinfacht). */
const reddit: IconFn = (size = 14) =>
  wrap(
    size,
    `<circle cx="12" cy="13.2" r="8.4" fill="none" stroke="currentColor" stroke-width="1.6"/>
     <circle cx="8.6" cy="13.6" r="1.35" fill="currentColor"/>
     <circle cx="15.4" cy="13.6" r="1.35" fill="currentColor"/>
     <path d="M8.2 16.6c1 .9 2.3 1.3 3.8 1.3s2.8-.4 3.8-1.3" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>
     <path d="M12 8.6V4.8m0 0 3-1.4M15 3.4a1.1 1.1 0 1 0 2.2 0 1.1 1.1 0 0 0-2.2 0Z" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/>
     <ellipse cx="20.3" cy="13.1" rx="1.9" ry="1.9" fill="none" stroke="currentColor" stroke-width="1.3"/>
     <ellipse cx="3.7" cy="13.1" rx="1.9" ry="1.9" fill="none" stroke="currentColor" stroke-width="1.3"/>`,
  );

/** Facebook - das "f"-Icon. */
const facebook: IconFn = (size = 14) =>
  wrap(
    size,
    `<path d="M21 12a9 9 0 1 0-10.4 8.9v-6.3H8.4V12h2.2V9.9c0-2.2 1.3-3.4 3.3-3.4.95 0 1.94.17 1.94.17v2.1h-1.1c-1.08 0-1.42.68-1.42 1.37V12h2.42l-.39 2.6h-2.03v6.3A9 9 0 0 0 21 12Z" fill="currentColor"/>`,
  );

/** News / RSS - klassisches Signal-Symbol. */
const news: IconFn = (size = 14) =>
  wrap(
    size,
    `<rect x="3" y="3" width="18" height="18" rx="4" fill="none" stroke="currentColor" stroke-width="1.6"/>
     <circle cx="7.6" cy="16.4" r="1.6" fill="currentColor"/>
     <path d="M7 11.4a6 6 0 0 1 6 6M7 7a10.4 10.4 0 0 1 10.4 10.4" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" fill="none"/>`,
  );

/** Generischer Platzhalter für unbekannte/zukünftige Plattformen. */
const generic: IconFn = (size = 14) =>
  wrap(
    size,
    `<circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="1.6"/>
     <path d="M12 8v5l3 2" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>`,
  );

const ICONS: Record<string, IconFn> = { x, bluesky, reddit, facebook, news };

export function platformIcon(platform: string, size = 14): string {
  const fn = ICONS[platform] ?? generic;
  return fn(size);
}

export const PLATFORM_LABEL: Record<string, string> = {
  x: "X",
  bluesky: "Bluesky",
  reddit: "Reddit",
  facebook: "Facebook",
  news: "News",
};

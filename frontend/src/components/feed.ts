import { PLATFORM_LABEL, platformIcon } from "../icons";
import type { Post } from "../types";
import { esc, highlight, num, relTime } from "../utils";

function engagementText(e: Record<string, number>): string {
  const parts: string[] = [];
  if (e.likes) parts.push(`♥ ${num(e.likes)}`);
  if (e.score) parts.push(`↑ ${num(e.score)}`);
  if (e.reposts) parts.push(`⇄ ${num(e.reposts)}`);
  if (e.comments) parts.push(`💬 ${num(e.comments)}`);
  if (e.replies) parts.push(`💬 ${num(e.replies)}`);
  if (e.shares) parts.push(`↗ ${num(e.shares)}`);
  return parts.join("  ");
}

export function postCard(p: Post, isNew = false): string {
  const platform = PLATFORM_LABEL[p.platform] ?? p.platform;
  const body = highlight(esc(p.text || ""), p.matched_terms);

  return `
  <article class="post ${esc(p.platform)} ${isNew ? "enter" : ""}" data-id="${p.id}">
    <div class="post-head">
      <span class="pbadge ${esc(p.platform)}">${platformIcon(p.platform, 12)}<span>${esc(platform)}</span></span>
      <span class="author">${esc(p.author || p.source || "unbekannt")}</span>
      ${p.author_handle && p.author_handle !== p.author ? `<span class="handle">${esc(p.author_handle)}</span>` : ""}
      ${p.source && p.source !== p.author ? `<span class="handle">· ${esc(p.source)}</span>` : ""}
      <span class="time" title="${esc(p.created_at ?? "")}">${relTime(p.collected_at)}</span>
    </div>

    ${p.title ? `<div class="post-title">${highlight(esc(p.title), p.matched_terms)}</div>` : ""}
    ${p.text ? `<div class="post-text">${body}</div>` : ""}

    <div class="post-foot">
      ${(p.categories || [])
        .slice(0, 3)
        .map((c) => `<span class="cat ${esc(c)}">${esc(c)}</span>`)
        .join("")}
      ${(p.cve_ids || [])
        .slice(0, 4)
        .map((c) => `<span class="cve">${esc(c)}</span>`)
        .join("")}
      ${
        p.matched_terms?.length
          ? `<span class="eng">match: ${p.matched_terms.slice(0, 3).map(esc).join(", ")}</span>`
          : ""
      }
      <span class="eng">${engagementText(p.engagement || {})}</span>
      ${
        p.url
          ? `<a class="srclink" href="${esc(p.url)}" target="_blank" rel="noopener noreferrer">Quelle öffnen ↗</a>`
          : ""
      }
    </div>
  </article>`;
}

export type FeedVariant = "list" | "grid";

export function squareCard(p: Post): string {
  const platform = PLATFORM_LABEL[p.platform] ?? p.platform;
  const tag = p.url ? "a" : "article";
  const linkAttrs = p.url ? ` href="${esc(p.url)}" target="_blank" rel="noopener noreferrer"` : "";
  return `
  <${tag} class="post-square ${esc(p.platform)}" data-id="${p.id}"${linkAttrs}>
    <span class="pbadge ${esc(p.platform)}">${platformIcon(p.platform, 12)}<span>${esc(platform)}</span></span>
    <div class="sq-title">${esc(p.title || p.text || "")}</div>
    <span class="sq-time">${relTime(p.collected_at)}</span>
  </${tag}>`;
}

export function renderFeed(el: HTMLElement, posts: Post[], hasFilter: boolean, variant: FeedVariant = "list"): void {
  el.classList.toggle("variant-grid", variant === "grid");

  if (!posts.length) {
    el.innerHTML = `
      <div class="empty">
        <span class="big">∅</span>
        ${
          hasFilter
            ? "Keine Treffer für diesen Filter.<br>Filter zurücksetzen oder Suchbegriff ergänzen."
            : "Warte auf den ersten Sammellauf …<br>Quellen links anklicken, um sofort zu sammeln."
        }
      </div>`;
    return;
  }

  if (variant === "grid") {
    el.innerHTML = posts.map((p) => squareCard(p)).join("");
    return;
  }
  el.innerHTML = posts.map((p) => postCard(p)).join("");
  attachExpand(el);
}

/** Klick auf gekürzten Text klappt ihn auf. */
export function attachExpand(el: HTMLElement): void {
  el.querySelectorAll<HTMLElement>(".post-text").forEach((node) => {
    if (node.dataset.bound) return;
    node.dataset.bound = "1";
    node.addEventListener("click", () => node.classList.toggle("expanded"));
  });
}

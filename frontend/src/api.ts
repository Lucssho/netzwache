import type { LogEntry, Post, SourceState, Stats, Term, UiSettings } from "./types";

const BASE = import.meta.env.VITE_API_BASE ?? "";

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  health: () => req<Record<string, unknown>>("/api/health"),

  posts: (params: Record<string, string | number>) => {
    const qs = new URLSearchParams(
      Object.entries(params)
        .filter(([, v]) => v !== "" && v !== "all" && v !== 0)
        .map(([k, v]) => [k, String(v)]),
    );
    return req<{ items: Post[]; total: number }>(`/api/posts?${qs}`);
  },

  stats: () => req<Stats>("/api/stats"),
  sources: () => req<SourceState[]>("/api/sources"),
  log: (limit = 30) => req<LogEntry[]>(`/api/log?limit=${limit}`),

  terms: () => req<Term[]>("/api/terms"),
  addTerm: (term: string, category: string) =>
    req<Term>("/api/terms", {
      method: "POST",
      body: JSON.stringify({ term, category, platforms: [], enabled: true }),
    }),
  patchTerm: (id: number, patch: Partial<Term>) =>
    req<Term>(`/api/terms/${id}`, { method: "PATCH", body: JSON.stringify(patch) }),
  deleteTerm: (id: number) => req<void>(`/api/terms/${id}`, { method: "DELETE" }),

  patchSource: (name: string, patch: { enabled?: boolean; interval_seconds?: number }) =>
    req<SourceState>(`/api/sources/${name}`, { method: "PATCH", body: JSON.stringify(patch) }),

  collectNow: (source?: string) =>
    req<{ ran: string[]; new: number }>(
      `/api/collect${source ? `?source=${encodeURIComponent(source)}` : ""}`,
      { method: "POST" },
    ),

  settings: () => req<UiSettings>("/api/settings"),
  putSettings: (values: Record<string, string>) =>
    req<UiSettings>("/api/settings", { method: "PUT", body: JSON.stringify({ values }) }),
};

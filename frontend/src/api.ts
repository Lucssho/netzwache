import type { LogEntry, Post, SourceState, StorageInfo, Stats, Term, UiSettings } from "./types";

const BASE = import.meta.env.VITE_API_BASE ?? "";

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    credentials: "include", // Session-Cookie mitschicken/empfangen (Admin-Login)
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

  // `term` = Fokus-Begriff (Trefferdefinition siehe termMatch.ts), `offset` zum Blättern.
  posts: (params: Record<string, string | number>) => {
    const qs = new URLSearchParams(
      Object.entries(params)
        .filter(([, v]) => v !== "" && v !== "all" && v !== 0)
        .map(([k, v]) => [k, String(v)]),
    );
    return req<{ items: Post[]; total: number }>(`/api/posts?${qs}`);
  },

  stats: (params?: { platform?: string; category?: string }) => {
    const qs = new URLSearchParams(
      Object.entries(params ?? {}).filter(([, v]) => v && v !== "all") as [string, string][],
    );
    const query = qs.toString();
    return req<Stats>(`/api/stats${query ? `?${query}` : ""}`);
  },
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

  storageInfo: () => req<StorageInfo>("/api/settings/storage"),
  deleteAllPosts: (confirm: string) =>
    req<{ removed: number }>("/api/maintenance/delete-all-posts", {
      method: "POST",
      body: JSON.stringify({ confirm }),
    }),

  authMe: () => req<{ authenticated: boolean }>("/api/auth/me"),
  authLogin: (username: string, password: string) =>
    req<{ authenticated: boolean }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  authLogout: () => req<{ authenticated: boolean }>("/api/auth/logout", { method: "POST" }),
};

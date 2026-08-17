export type Category = "cybersecurity" | "it" | "nachrichten" | "alltag";

export interface Post {
  id: number;
  platform: string;
  source: string;
  external_id: string;
  author: string;
  author_handle: string;
  title: string;
  text: string;
  url: string;
  lang: string;
  created_at: string | null;
  collected_at: string | null;
  categories: string[];
  matched_terms: string[];
  keywords: string[];
  cve_ids: string[];
  severity: number;
  engagement: Record<string, number>;
}

export interface SourceState {
  name: string;
  platform: string;
  label: string;
  enabled: boolean;
  status: "idle" | "ok" | "error" | "disabled" | "degraded";
  detail: string;
  interval_seconds: number;
  last_run_at: string | null;
  last_success_at: string | null;
  last_duration_ms: number;
  items_last_run: number;
  items_total: number;
  errors_total: number;
  consecutive_errors: number;
  setup_hint?: string;
}

export interface Term {
  id: number;
  term: string;
  category: string;
  platforms: string[];
  enabled: boolean;
  hits: number;
  last_hit_at: string | null;
  created_at: string | null;
}

export interface Stats {
  total: number;
  by_platform: Record<string, number>;
  by_category: Record<string, number>;
  last_hour: number;
  last_5min: number;
  per_minute: number;
  high_severity: number;
  top_keywords: [string, number][];
  top_cves: [string, number][];
  series: number[];
  uptime_seconds: number;
  ticks: number;
}

export interface LogEntry {
  id: number;
  ts: string | null;
  level: string;
  source: string;
  message: string;
}

export interface Filters {
  platform: string;
  category: string;
  query: string;
  minSeverity: number;
  paused: boolean;
}

export type FontKey = "jetbrains" | "fira" | "sfmono" | "menlo" | "consolas" | "inter" | "system";
export type Density = "compact" | "comfortable" | "relaxed";

export interface UiSettings {
  font_family: FontKey;
  font_size: string;
  density: Density;
  theme: string;
  [key: string]: string;
}

export interface CredentialStatus {
  configured: boolean;
  mode?: string;
  handle?: string | null;
  client_id?: string | null;
  app_password?: string | null;
  bearer_token?: string | null;
}

export interface KnownIssue {
  id: string;
  title: string;
  symptom: string;
  fix: string;
}

export interface Diagnostics {
  database: { ok: boolean; engine: string };
  redis: { connected: boolean; backend: string };
  websocket_clients: number;
  credentials: Record<string, CredentialStatus>;
  known_issues: KnownIssue[];
}

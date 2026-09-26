// Server-side client for the dashboard API (services/api/dashboard). The dashboard shows what the
// API returns and never recomputes a finding's type, severity or confidence.

import { redirect } from "next/navigation";
import { clientIp, getToken } from "./session";

export const API_URL = process.env.DBINSIGHT_API_URL ?? "http://localhost:8710";

export type Level = "LOW" | "MEDIUM" | "HIGH";
export type Layer =
  | "STATIC_SOURCE"
  | "DECLARED_SCHEMA"
  | "ACTUAL_SCHEMA"
  | "SQL"
  | "RUNTIME"
  | "DATA_QUALITY";

export interface Evidence {
  source: Layer;
  description: string;
  file?: string;
  line?: number;
  data?: Record<string, unknown>;
}

export interface Finding {
  finding_id: string;
  rule_id: string;
  severity: Level;
  confidence: Level;
  file: string;
  line: number;
  end_line: number | null;
  title: string;
  body: string;
  evidence: Evidence[];
  layers: Layer[];
  suggested_fix: string | null;
  fingerprint: string;
}

export interface ScanCounts {
  high: number;
  medium: number;
  low: number;
  total: number;
}

export interface ScanRow extends ScanCounts {
  scan_id: string;
  app: string;
  started_at: string;
  finished_at: string | null;
  status: "running" | "ok" | "failed";
  error: string | null;
  layers: string[];
  git_commit: string | null;
  git_dirty: boolean | null;
}

export interface ScanSummary {
  scan_id: string;
  app: string;
  started_at: string;
  finished_at: string | null;
  status: string;
  layers: string[];
  layer_seconds: Record<string, number>;
  git_commit: string | null;
  git_dirty: boolean | null;
  kind: "app" | "project";
  source: ProjectSource | null;
  counts: ScanCounts;
}

export interface ProjectSource {
  kind: "local" | "git";
  origin: string;
  commit: string | null;
  dirty: boolean | null;
  schema_path: string | null;
  schema_candidates: { path: string; models: number; postgresql: boolean }[];
  notes: string[];
  coverage: { source_files: number; orm_operations: number } | null;
}

export interface AppRow {
  app: string;
  kind: "app" | "project";
  source: ProjectSource | null;
  latest_scan: ScanRow | null;
}

export interface FingerprintStat {
  fingerprint: string;
  sql: string;
  executions: number;
  mean_ms: number;
  p95_ms: number;
  max_ms: number;
  total_ms: number;
  routes: string[] | null;
}

export interface RouteRepetition {
  route: string;
  requests: number;
  mean_repeats: number;
  max_repeats: number;
  repeated_sql: string;
}

export interface QueryAnalytics {
  statements: number;
  distinct_fingerprints: number;
  slowest: FingerprintStat[];
  most_frequent: FingerprintStat[];
  endpoint_repetition: RouteRepetition[];
}

export interface Detection {
  detector: string;
  evaluated: boolean;
  anomalous: boolean;
  lower: number | null;
  upper: number | null;
  center: number | null;
}

export interface MetricView {
  metric: "null_rate" | "duplicate_rate" | "distribution_shift";
  observation: number;
  anomalous: boolean;
  direction: string | null;
  fired: number;
  evaluated: number;
  detections: Detection[];
  explanation: { categories?: { value: string; baselineShare: number; currentShare: number }[] };
}

export interface ColumnQuality {
  table: string;
  column: string;
  rows: number | null;
  null_rate: number | null;
  duplicate_rate: number | null;
  distinct: number | null;
  metrics: MetricView[];
}

export interface IndexDivergence {
  kind: string;
  line: number | null;
  model: string | null;
  table: string;
  columns: string[];
  index_name: string | null;
  definition: string | null;
}

export interface SchemaView {
  /** `actual` and `divergence` are null for a scanned project: there is no database to read. */
  declared: {
    model: string;
    table: string;
    fields: { name: string; column: string; type: string; optional: boolean }[];
    indexes: { kind: string; columns: string[]; line: number }[];
  }[];
  actual: {
    table: string;
    columns: { name: string; type: string; nullable: boolean }[];
    indexes: { name: string; columns: string[]; kind: string }[];
  }[] | null;
  divergence: {
    indexes_not_declared: IndexDivergence[];
    declared_indexes_not_applied: IndexDivergence[];
    column_mismatches: unknown[];
    tables_not_applied: string[];
    tables_not_declared: string[];
    foreign_keys_not_applied: { table: string; columns: string[]; referenced_table: string }[];
    foreign_keys_not_declared: { table: string; columns: string[]; referenced_table: string }[];
  } | null;
}

export class ApiError extends Error {
  constructor(message: string, public status?: number) {
    super(message);
  }
}

export interface User {
  id: string;
  email: string;
  name: string;
  role: "user" | "admin";
  created_at: string;
  can_scan_local: boolean;
}

/** Headers that identify the signed-in visitor to the API. */
export async function authHeaders(): Promise<Record<string, string>> {
  const token = await getToken();
  const ip = await clientIp();
  return { ...(token ? { authorization: `Bearer ${token}` } : {}), ...(ip ? { "x-client-ip": ip } : {}) };
}

async function get<T>(path: string): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, { cache: "no-store", headers: await authHeaders() });
  } catch {
    throw new ApiError(
      `Cannot reach the dashboard API at ${API_URL}. Start it with: cd services && uv run uvicorn api.dashboard.app:app --port 8710`,
    );
  }
  if (response.status === 401) redirect("/login?expired=1");
  if (!response.ok) throw new ApiError(`${path}: ${response.status} ${await response.text()}`, response.status);
  return response.json() as Promise<T>;
}

/** The signed-in user, or null when signed out (no cookie, expired, or revoked). */
export async function currentUser(): Promise<User | null> {
  if (!(await getToken())) return null;
  try {
    const response = await fetch(`${API_URL}/v1/auth/me`, { cache: "no-store", headers: await authHeaders() });
    return response.ok ? ((await response.json()) as User) : null;
  } catch {
    throw new ApiError(`Cannot reach the dashboard API at ${API_URL}. Start it with: cd services && uv run uvicorn api.dashboard.app:app --port 8710`);
  }
}

export async function requireUser(): Promise<User> {
  const user = await currentUser();
  if (!user) redirect("/login?expired=1");
  return user;
}

export const api = {
  apps: () => get<AppRow[]>("/v1/apps"),
  scans: (app: string) => get<ScanRow[]>(`/v1/apps/${app}/scans`),
  scan: (id: string) => get<ScanSummary>(`/v1/scans/${id}`),
  findings: (id: string, filters: Record<string, string | undefined> = {}) => {
    const query = new URLSearchParams(
      Object.entries(filters).filter((entry): entry is [string, string] => Boolean(entry[1])),
    ).toString();
    return get<Finding[]>(`/v1/scans/${id}/findings${query ? `?${query}` : ""}`);
  },
  finding: (id: string, findingId: string) => get<Finding>(`/v1/scans/${id}/findings/${findingId}`),
  queries: (id: string) => get<QueryAnalytics | null>(`/v1/scans/${id}/queries`),
  dataQuality: (id: string) => get<ColumnQuality[] | null>(`/v1/scans/${id}/data-quality`),
  schema: (id: string) => get<SchemaView>(`/v1/scans/${id}/schema`),
};

/** The scan a page shows: the one in `?scan=`, else the app's latest successful scan. */
export async function resolveScan(app: string, scan?: string): Promise<ScanRow | null> {
  const scans = await api.scans(app);
  const ok = scans.filter((s) => s.status === "ok");
  return (scan ? ok.find((s) => s.scan_id === scan) : ok[0]) ?? null;
}

/** Scan layer ids (as the scan records them) to the evidence source they produce. */
export const SCAN_LAYER_TO_SOURCE: Record<string, Layer> = {
  static_orm: "STATIC_SOURCE",
  sql: "SQL",
  declared: "DECLARED_SCHEMA",
  actual: "ACTUAL_SCHEMA",
  runtime: "RUNTIME",
  data: "DATA_QUALITY",
};

export const isProject = (row: { kind: string }) => row.kind === "project";

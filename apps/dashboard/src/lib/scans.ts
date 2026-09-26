import { api, resolveScan, SCAN_LAYER_TO_SOURCE, type Finding, type Layer, type ScanRow, type ScanSummary } from "./api";

export interface ScanContext {
  scan: ScanRow;
  summary: ScanSummary;
  history: ScanRow[];
  previous: ScanRow | null;
  ran: Layer[];
}

/** The scan a page shows, its summary, and the scan before it (for "since the last scan"). */
export async function loadScan(app: string, scanParam?: string): Promise<ScanContext | null> {
  const scan = await resolveScan(app, scanParam);
  if (!scan) return null;
  const [summary, history] = await Promise.all([api.scan(scan.scan_id), api.scans(app)]);
  const ok = history.filter((s) => s.status === "ok");
  const index = ok.findIndex((s) => s.scan_id === scan.scan_id);
  return {
    scan,
    summary,
    history: ok,
    previous: index >= 0 ? (ok[index + 1] ?? null) : null,
    ran: summary.layers.map((l) => SCAN_LAYER_TO_SOURCE[l]).filter(Boolean),
  };
}

/** Findings that are new in `current` and findings that were in `previous` and are gone. */
export function diffFindings(current: Finding[], previous: Finding[] | null) {
  if (!previous) return { added: new Set<string>(), resolved: [] as Finding[] };
  const before = new Set(previous.map((f) => f.fingerprint));
  const now = new Set(current.map((f) => f.fingerprint));
  return {
    added: new Set(current.filter((f) => !before.has(f.fingerprint)).map((f) => f.fingerprint)),
    resolved: previous.filter((f) => !now.has(f.fingerprint)),
  };
}

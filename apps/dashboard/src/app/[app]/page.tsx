import Link from "next/link";
import { ApiProblem, Card, NoScan } from "@/components/Page";
import { ConfidenceBadge, LayerChip, SeverityBadge } from "@/components/Badges";
import { TrendChart } from "@/components/Charts";
import { api, resolveScan, type Finding, type ScanRow, type ScanSummary } from "@/lib/api";
import { LAYERS } from "@/lib/ui";

export const dynamic = "force-dynamic";

export default async function Health({
  params,
  searchParams,
}: {
  params: Promise<{ app: string }>;
  searchParams: Promise<{ scan?: string }>;
}) {
  const { app } = await params;
  const { scan: scanParam } = await searchParams;
  let scan: ScanRow | null;
  let summary: ScanSummary | null = null;
  let findings: Finding[] = [];
  let history: ScanRow[] = [];
  try {
    scan = await resolveScan(app, scanParam);
    if (scan) {
      [summary, findings, history] = await Promise.all([api.scan(scan.scan_id), api.findings(scan.scan_id), api.scans(app)]);
    }
  } catch (error) {
    return <ApiProblem error={error} />;
  }
  if (!scan || !summary) return <NoScan app={app} />;

  const byLayer = LAYERS.map((l) => ({ ...l, count: findings.filter((f) => f.layers.includes(l.id)).length }));
  const multi = findings.filter((f) => f.layers.length >= 3).length;
  const trend = history
    .filter((s) => s.status === "ok")
    .slice()
    .reverse()
    .map((s) => ({ label: new Date(s.started_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }), high: s.high, medium: s.medium, low: s.low }));
  const top = findings.slice(0, 5);

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {[
          ["Findings", summary.counts.total, "text-slate-900"],
          ["High", summary.counts.high, "text-red-700"],
          ["Medium", summary.counts.medium, "text-orange-700"],
          ["Backed by 3+ layers", multi, "text-emerald-700"],
        ].map(([label, value, color]) => (
          <div key={String(label)} className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
            <div className="text-xs uppercase tracking-wide text-slate-500">{label}</div>
            <div className={`mt-1 text-3xl font-semibold ${color}`}>{value}</div>
          </div>
        ))}
      </div>

      <div className="grid gap-5 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <Card title="Findings by severity, per scan" note={`${trend.length} scan${trend.length === 1 ? "" : "s"}`}>
            <TrendChart data={trend} />
          </Card>
        </div>
        <Card title="Findings by contributing layer" note="a finding can count under several">
          <ul className="space-y-2">
            {byLayer.map((l) => (
              <li key={l.id} className="flex items-center justify-between text-sm">
                <LayerChip layer={l.id} />
                <span className="tabular-nums text-slate-700">{l.count}</span>
              </li>
            ))}
          </ul>
          <p className="mt-3 text-xs text-slate-500">
            Layer time: {Object.entries(summary.layer_seconds).map(([k, v]) => `${k} ${v.toFixed(1)}s`).join(" · ")}
          </p>
        </Card>
      </div>

      <Card title="Most severe findings" note="open one to see its full evidence chain">
        <ul className="divide-y divide-slate-100">
          {top.map((f) => (
            <li key={f.finding_id} className="py-3">
              <Link href={`/${app}/findings/${f.finding_id}?scan=${scan.scan_id}`} className="block hover:bg-slate-50">
                <div className="flex flex-wrap items-center gap-2">
                  <SeverityBadge level={f.severity} />
                  <ConfidenceBadge level={f.confidence} />
                  <span className="text-sm font-medium">{f.title}</span>
                </div>
                <div className="mt-1 flex flex-wrap gap-1">
                  {f.layers.map((l) => <LayerChip key={l} layer={l} />)}
                </div>
              </Link>
            </li>
          ))}
        </ul>
      </Card>
      <p className="text-xs text-slate-400">
        Scan {scan.scan_id.slice(0, 8)} · {new Date(scan.started_at).toLocaleString()} · code {summary.git_commit}{summary.git_dirty ? " (uncommitted changes)" : ""}
      </p>
    </div>
  );
}

import Link from "next/link";
import { ApiProblem, Card, NoScan } from "@/components/Page";
import { ConfidenceBadge, LayerChip, SeverityBadge } from "@/components/Badges";
import { TrendChart } from "@/components/Charts";
import { api, resolveScan, SCAN_LAYER_TO_SOURCE, type Finding, type ScanRow, type ScanSummary } from "@/lib/api";
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

  const ran = new Set(summary.layers.map((l) => SCAN_LAYER_TO_SOURCE[l]));
  const byLayer = LAYERS.map((l) => ({ ...l, run: ran.has(l.id), count: findings.filter((f) => f.layers.includes(l.id)).length }));
  const multi = findings.filter((f) => f.layers.length >= 3).length;
  const trend = history
    .filter((s) => s.status === "ok")
    .slice()
    .reverse()
    .map((s) => ({ label: new Date(s.started_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }), high: s.high, medium: s.medium, low: s.low }));
  const top = findings.slice(0, 5);

  const source = summary.source;
  const located = source?.coverage?.orm_operations;
  return (
    <div className="space-y-5">
      {summary.kind === "project" && source && (
        <div className="space-y-3">
          {located === 0 && (
            <div className="rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-900">
              <p className="font-medium">The analyzer found no Prisma operations in this project.</p>
              <p className="mt-1">
                It loaded {source.coverage?.source_files} source files and located none, so having no findings here is not evidence of clean code:
                the analyzer probably did not recognise how this project creates its Prisma client (for example a client imported from another
                package, a class that extends PrismaClient, or a wrapper it cannot follow).
              </p>
            </div>
          )}
          <div className="rounded-lg border border-slate-200 bg-white p-4 text-sm shadow-sm">
            <div className="grid gap-x-8 gap-y-1 sm:grid-cols-2">
              <div><span className="text-slate-500">Source: </span><code className="break-all">{source.origin}</code> ({source.kind})</div>
              <div><span className="text-slate-500">Commit: </span><code>{source.commit ? source.commit.slice(0, 10) : "not a git repository"}</code>{source.dirty ? " (uncommitted changes)" : ""}</div>
              <div><span className="text-slate-500">Schema: </span><code>{source.schema_path ?? "none found"}</code></div>
              <div><span className="text-slate-500">Analyzed: </span>{source.coverage ? `${source.coverage.source_files} files, ${source.coverage.orm_operations} Prisma operations located` : "n/a"}</div>
            </div>
            <p className="mt-2 text-xs text-slate-500">Layers run: {summary.layers.join(", ")}. Runtime, actual-schema and data-quality layers need a running application and were not run.</p>
            {source.notes.map((n) => <p key={n} className="mt-1 text-xs text-amber-800">Note: {n}</p>)}
          </div>
        </div>
      )}
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
                {l.run ? <span className="tabular-nums text-slate-700">{l.count}</span> : <span className="text-xs text-slate-400">not run</span>}
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

import { unstable_rethrow } from "next/navigation";
import Link from "next/link";
import { SeverityDonut, SeverityTrend, HorizontalBars } from "@/components/charts/Charts";
import { Card } from "@/components/ui/Card";
import { ConfidenceMeter, LayerChip, SeverityBadge, SEVERITY_COLOR } from "@/components/ui/Badge";
import { Icon } from "@/components/ui/icons";
import { ApiProblem, NoScan } from "@/components/ui/State";
import { Stat } from "@/components/ui/Stat";
import { api, type Finding, type Level } from "@/lib/api";
import { diffFindings, loadScan, type ScanContext } from "@/lib/scans";
import { LAYERS, shortTime } from "@/lib/ui";

export const dynamic = "force-dynamic";

const RANK: Record<Level, number> = { HIGH: 0, MEDIUM: 1, LOW: 2 };

export default async function Overview({ params, searchParams }: { params: Promise<{ app: string }>; searchParams: Promise<{ scan?: string }> }) {
  const { app } = await params;
  const { scan: scanParam } = await searchParams;
  let ctx: ScanContext | null;
  let findings: Finding[] = [];
  let before: Finding[] | null = null;
  try {
    ctx = await loadScan(app, scanParam);
    if (ctx) [findings, before] = await Promise.all([api.findings(ctx.scan.scan_id), ctx.previous ? api.findings(ctx.previous.scan_id) : Promise.resolve(null)]);
  } catch (error) {
    unstable_rethrow(error);
    return <ApiProblem error={error} />;
  }
  if (!ctx) return <NoScan app={app} />;

  const { scan, summary, history, previous, ran } = ctx;
  const { added, resolved } = diffFindings(findings, before);
  const chronological = history.slice().reverse();
  const trend = chronological.map((s) => ({ label: shortTime(s.started_at), high: s.high, medium: s.medium, low: s.low }));
  const source = summary.source;
  const located = source?.coverage?.orm_operations;

  const rules = new Map<string, { count: number; worst: Level }>();
  for (const f of findings) {
    const r = rules.get(f.rule_id) ?? { count: 0, worst: "LOW" as Level };
    r.count += 1;
    if (RANK[f.severity] < RANK[r.worst]) r.worst = f.severity;
    rules.set(f.rule_id, r);
  }
  const ruleBars = [...rules.entries()].sort((a, b) => b[1].count - a[1].count).map(([name, r]) => ({ name, value: r.count, color: SEVERITY_COLOR[r.worst] }));
  const ranSet = new Set(ran);
  const top = findings.slice(0, 5);

  return (
    <div className="space-y-6">
      {summary.kind === "project" && located === 0 && (
        <div role="alert" className="flex gap-3 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-900 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-200">
          <Icon name="alert" className="mt-0.5 h-5 w-5 shrink-0" />
          <div>
            <p className="font-semibold">The analyzer found no Prisma operations in this project.</p>
            <p className="mt-1 opacity-90">It loaded {source?.coverage?.source_files} source files and located none, so having no findings here is not evidence of clean code. It probably did not recognise how this project creates its Prisma client (for example a client imported from another package, a class that extends PrismaClient, or a wrapper it cannot follow).</p>
          </div>
        </div>
      )}
      {source?.notes.map((n) => (
        <div key={n} className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-200"><Icon name="info" className="mt-0.5 h-4 w-4 shrink-0" />{n}</div>
      ))}

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat label="Findings" value={summary.counts.total} previous={previous?.total} history={chronological.map((s) => s.total)} />
        <Stat label="High severity" value={summary.counts.high} previous={previous?.high} history={chronological.map((s) => s.high)} tone={summary.counts.high ? "red" : "green"} />
        <Stat label="Medium severity" value={summary.counts.medium} previous={previous?.medium} history={chronological.map((s) => s.medium)} tone="amber" />
        <div className="rounded-xl border border-line bg-surface p-4 shadow-card">
          <div className="text-xs font-medium uppercase tracking-wide text-muted">Since the previous scan</div>
          {before ? (
            <div className="mt-2 flex items-baseline gap-5">
              <div><span className="text-3xl font-semibold tabular-nums text-red-600 dark:text-red-400">{added.size}</span><span className="ml-1.5 text-xs text-muted">new</span></div>
              <div><span className="text-3xl font-semibold tabular-nums text-emerald-600 dark:text-emerald-400">{resolved.length}</span><span className="ml-1.5 text-xs text-muted">resolved</span></div>
            </div>
          ) : (
            <div className="mt-2 text-sm text-muted">This is the first scan, so there is nothing to compare with yet.</div>
          )}
          {before && added.size > 0 && (
            <Link href={`/${app}/findings?scan=${scan.scan_id}&only=new`} className="mt-1 inline-block text-xs text-brand hover:underline">Show the new findings</Link>
          )}
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card title="Findings over time" note={`${trend.length} scan${trend.length === 1 ? "" : "s"}, stacked by severity`} className="lg:col-span-2">
          <SeverityTrend data={trend} />
          {trend.length < 2 && <p className="mt-1 text-xs text-muted">A trend line appears once this has been scanned at least twice.</p>}
        </Card>
        <Card title="Severity mix" note="This scan">
          <SeverityDonut high={summary.counts.high} medium={summary.counts.medium} low={summary.counts.low} />
        </Card>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Findings by rule" note="Bar colour is the most severe finding of that rule">
          {ruleBars.length ? <HorizontalBars data={ruleBars} unit="findings" nameWidth={210} /> : <p className="text-sm text-muted">No findings in this scan.</p>}
        </Card>
        <Card title="Evidence layers" note="Which layers ran, and how many findings each one backs">
          <ul className="divide-y divide-line">
            {LAYERS.map((l) => {
              const run = ranSet.has(l.id);
              const key = Object.entries({ static_orm: "STATIC_SOURCE", sql: "SQL", declared: "DECLARED_SCHEMA", actual: "ACTUAL_SCHEMA", runtime: "RUNTIME", data: "DATA_QUALITY" }).find(([, v]) => v === l.id)?.[0] ?? "";
              const seconds = summary.layer_seconds[key];
              const backed = findings.filter((f) => f.layers.includes(l.id)).length;
              return (
                <li key={l.id} className="flex items-center gap-3 py-2.5 text-sm">
                  <LayerChip layer={l.id} muted={!run} />
                  {run ? (
                    <>
                      <span className="ml-auto tabular-nums text-ink">{backed}</span>
                      <span className="w-10 text-right text-xs tabular-nums text-faint">{seconds !== undefined ? `${seconds.toFixed(1)}s` : ""}</span>
                    </>
                  ) : (
                    <span className="ml-auto text-xs text-faint">not run for this scan</span>
                  )}
                </li>
              );
            })}
          </ul>
        </Card>
      </div>

      <Card title="Most severe findings" note="Open one to see its full evidence chain" action={<Link href={`/${app}/findings?scan=${scan.scan_id}`} className="text-xs font-medium text-brand hover:underline">All findings</Link>} padded={false}>
        {top.length === 0 ? (
          <p className="p-5 text-sm text-muted">No findings in this scan.</p>
        ) : (
          <ul className="divide-y divide-line">
            {top.map((f) => (
              <li key={f.finding_id}>
                <Link href={`/${app}/findings/${f.finding_id}?scan=${scan.scan_id}`} className="block px-5 py-3.5 hover:bg-sunken">
                  <div className="flex flex-wrap items-center gap-2">
                    <SeverityBadge level={f.severity} />
                    <ConfidenceMeter level={f.confidence} showLabel={false} />
                    <span className="text-sm font-medium text-ink">{f.title}</span>
                  </div>
                  <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                    <code className="mr-1 font-mono text-[11px] text-muted">{f.file}{f.line ? `:${f.line}` : ""}</code>
                    {f.layers.map((l) => <LayerChip key={l} layer={l} size="xs" />)}
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <p className="text-xs text-faint">
        Scan {scan.scan_id.slice(0, 8)} · {new Date(scan.started_at).toLocaleString()} · analyzer code {summary.git_commit}{summary.git_dirty ? " (uncommitted changes)" : ""}
        {source?.commit ? ` · project commit ${source.commit.slice(0, 10)}` : ""}
      </p>
    </div>
  );
}

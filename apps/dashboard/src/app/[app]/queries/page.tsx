import { HorizontalBars } from "@/components/charts/Charts";
import { Card } from "@/components/ui/Card";
import { NeedsDatabase, ApiProblem, NoScan } from "@/components/ui/State";
import { api, type QueryAnalytics } from "@/lib/api";
import { loadScan, type ScanContext } from "@/lib/scans";
import { fmtMs, shapeLabel } from "@/lib/ui";

export const dynamic = "force-dynamic";

export default async function Queries({ params, searchParams }: { params: Promise<{ app: string }>; searchParams: Promise<{ scan?: string }> }) {
  const { app } = await params;
  const { scan: scanParam } = await searchParams;
  let ctx: ScanContext | null;
  let q: QueryAnalytics | null = null;
  try {
    ctx = await loadScan(app, scanParam);
    if (ctx) q = await api.queries(ctx.scan.scan_id);
  } catch (error) {
    return <ApiProblem error={error} />;
  }
  if (!ctx) return <NoScan app={app} />;
  if (!q) return <NeedsDatabase view="Query analytics" needs="runtime capture from a running application" />;

  const worst = q.endpoint_repetition[0];
  const maxRepeats = Math.max(1, ...q.endpoint_repetition.map((r) => r.max_repeats));
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {[
          ["Statements recorded", q.statements],
          ["Distinct query shapes", q.distinct_fingerprints],
          ["Endpoints observed", q.endpoint_repetition.length],
          ["Worst repetition", worst ? `${worst.max_repeats}x` : "n/a"],
        ].map(([label, value]) => (
          <div key={String(label)} className="rounded-xl border border-line bg-surface p-4 shadow-card">
            <div className="text-xs font-medium uppercase tracking-wide text-muted">{label}</div>
            <div className="mt-2 text-3xl font-semibold tabular-nums tracking-tight text-ink">{value}</div>
            {label === "Worst repetition" && worst && <div className="mt-1 truncate font-mono text-[11px] text-muted" title={worst.route}>{worst.route}</div>}
          </div>
        ))}
      </div>
      <p className="text-sm text-muted">Recorded by the runtime collector during this scan&apos;s load run. A shape is a query with its parameters removed, so the same query with different values counts once.</p>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Most repeated within one request" note="The N+1 signal, per endpoint">
          <HorizontalBars color="#ef4444" unit="executions in one request" nameWidth={190}
            data={q.endpoint_repetition.slice(0, 10).map((r) => ({ name: r.route, value: r.max_repeats, detail: r.repeated_sql }))} />
        </Card>
        <Card title="Most frequent query shapes" note="Total executions">
          <HorizontalBars color="var(--brand)" unit="executions" nameWidth={190}
            data={q.most_frequent.slice(0, 10).map((s) => ({ name: shapeLabel(s.sql), value: s.executions, detail: s.sql }))} />
        </Card>
      </div>

      <Card title="Per-endpoint repetition" note="The worst repeat of a single query shape within one request" padded={false}>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-line bg-sunken text-xs uppercase tracking-wide text-muted">
              <tr><th className="px-5 py-2.5 font-medium">Endpoint</th><th className="px-3 font-medium">Requests</th><th className="px-3 font-medium">Mean</th><th className="px-3 font-medium">Worst</th><th className="px-5 font-medium">Repeated query</th></tr>
            </thead>
            <tbody className="divide-y divide-line">
              {q.endpoint_repetition.map((r) => (
                <tr key={r.route} className={r.max_repeats >= 10 ? "bg-red-50/60 dark:bg-red-500/5" : ""}>
                  <td className="px-5 py-2.5 font-mono text-xs text-ink">{r.route}</td>
                  <td className="px-3 tabular-nums text-muted">{r.requests}</td>
                  <td className="px-3 tabular-nums text-muted">{r.mean_repeats.toFixed(1)}</td>
                  <td className="px-3">
                    <div className="flex items-center gap-2">
                      <div className="h-1.5 w-20 rounded-full bg-sunken"><div className={`h-1.5 rounded-full ${r.max_repeats >= 10 ? "bg-red-500" : "bg-slate-400"}`} style={{ width: `${(r.max_repeats / maxRepeats) * 100}%` }} /></div>
                      <span className="tabular-nums font-medium text-ink">{r.max_repeats}</span>
                    </div>
                  </td>
                  <td className="max-w-md truncate px-5 font-mono text-xs text-muted" title={r.repeated_sql}>{r.repeated_sql}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <Card title="Slowest query shapes" note="By 95th-percentile duration" padded={false}>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-line bg-sunken text-xs uppercase tracking-wide text-muted">
              <tr><th className="px-5 py-2.5 font-medium">Query shape</th><th className="px-3 font-medium">p95</th><th className="px-3 font-medium">Mean</th><th className="px-3 font-medium">Max</th><th className="px-3 font-medium">Runs</th><th className="px-5 font-medium">Total</th></tr>
            </thead>
            <tbody className="divide-y divide-line">
              {q.slowest.map((s) => (
                <tr key={s.fingerprint}>
                  <td className="max-w-xl truncate px-5 py-2.5 font-mono text-xs text-ink" title={s.sql}>{s.sql}</td>
                  <td className="px-3 tabular-nums text-ink">{fmtMs(s.p95_ms)}</td>
                  <td className="px-3 tabular-nums text-muted">{fmtMs(s.mean_ms)}</td>
                  <td className="px-3 tabular-nums text-muted">{fmtMs(s.max_ms)}</td>
                  <td className="px-3 tabular-nums text-muted">{s.executions}</td>
                  <td className="px-5 tabular-nums text-muted">{fmtMs(s.total_ms)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

import { ApiProblem, Card, NoScan } from "@/components/Page";
import { HorizontalBars } from "@/components/Charts";
import { api, resolveScan, type QueryAnalytics, type ScanRow } from "@/lib/api";
import { fmtMs, shapeLabel } from "@/lib/ui";

export const dynamic = "force-dynamic";

export default async function Queries({ params, searchParams }: { params: Promise<{ app: string }>; searchParams: Promise<{ scan?: string }> }) {
  const { app } = await params;
  const { scan: scanParam } = await searchParams;
  let scan: ScanRow | null;
  let q: QueryAnalytics | null = null;
  try {
    scan = await resolveScan(app, scanParam);
    if (scan) q = await api.queries(scan.scan_id);
  } catch (error) {
    return <ApiProblem error={error} />;
  }
  if (!scan || !q) return <NoScan app={app} />;

  return (
    <div className="space-y-5">
      <p className="text-sm text-slate-600">
        {q.statements} statements in {q.distinct_fingerprints} distinct shapes, recorded by the runtime collector during this scan&apos;s load run.
        A shape is a query with its parameters removed, so the same query with different values counts once.
      </p>
      <div className="grid gap-5 lg:grid-cols-2">
        <Card title="Most repeated within one request" note="the N+1 signal, per endpoint">
          <HorizontalBars
            color="#dc2626"
            unit="executions in one request"
            data={q.endpoint_repetition.slice(0, 10).map((r) => ({ name: r.route, value: r.max_repeats, detail: r.repeated_sql }))}
          />
        </Card>
        <Card title="Most frequent query shapes" note="executions">
          <HorizontalBars
            color="#2563eb"
            unit="executions"
            data={q.most_frequent.slice(0, 10).map((s) => ({ name: shapeLabel(s.sql), value: s.executions, detail: s.sql }))}
          />
        </Card>
      </div>

      <Card title="Per-endpoint repetition" note="worst repeat of one query shape in a single request">
        <table className="w-full text-left text-sm">
          <thead className="text-xs uppercase text-slate-500"><tr><th className="py-1">Endpoint</th><th>Requests</th><th>Mean repeats</th><th>Max repeats</th><th>Repeated query</th></tr></thead>
          <tbody className="divide-y divide-slate-100">
            {q.endpoint_repetition.map((r) => (
              <tr key={r.route} className={r.max_repeats >= 10 ? "bg-red-50" : ""}>
                <td className="py-1.5 font-mono text-xs">{r.route}</td>
                <td className="tabular-nums">{r.requests}</td>
                <td className="tabular-nums">{r.mean_repeats.toFixed(1)}</td>
                <td className="font-medium tabular-nums">{r.max_repeats}</td>
                <td className="max-w-md truncate font-mono text-xs text-slate-600" title={r.repeated_sql}>{r.repeated_sql}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <Card title="Slowest query shapes" note="by 95th-percentile duration">
        <table className="w-full text-left text-sm">
          <thead className="text-xs uppercase text-slate-500"><tr><th className="py-1">Query shape</th><th>p95</th><th>Mean</th><th>Max</th><th>Runs</th><th>Total</th></tr></thead>
          <tbody className="divide-y divide-slate-100">
            {q.slowest.map((s) => (
              <tr key={s.fingerprint}>
                <td className="max-w-xl truncate py-1.5 font-mono text-xs" title={s.sql}>{s.sql}</td>
                <td className="tabular-nums">{fmtMs(s.p95_ms)}</td>
                <td className="tabular-nums">{fmtMs(s.mean_ms)}</td>
                <td className="tabular-nums">{fmtMs(s.max_ms)}</td>
                <td className="tabular-nums">{s.executions}</td>
                <td className="tabular-nums">{fmtMs(s.total_ms)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

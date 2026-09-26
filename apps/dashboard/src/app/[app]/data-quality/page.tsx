import Link from "next/link";
import { Card } from "@/components/ui/Card";
import { RangeBar } from "@/components/RangeBar";
import { EmptyState, NeedsDatabase, ApiProblem, NoScan } from "@/components/ui/State";
import { api, type ColumnQuality } from "@/lib/api";
import { loadScan, type ScanContext } from "@/lib/scans";
import { pct } from "@/lib/ui";

export const dynamic = "force-dynamic";

const LABEL = { null_rate: "NULL rate", duplicate_rate: "Duplicate rate", distribution_shift: "Distribution shift" } as const;

export default async function DataQuality({ params, searchParams }: { params: Promise<{ app: string }>; searchParams: Promise<{ scan?: string; all?: string }> }) {
  const { app } = await params;
  const sp = await searchParams;
  let ctx: ScanContext | null;
  let columns: ColumnQuality[] | null = [];
  try {
    ctx = await loadScan(app, sp.scan);
    if (ctx) columns = await api.dataQuality(ctx.scan.scan_id);
  } catch (error) {
    return <ApiProblem error={error} />;
  }
  if (!ctx) return <NoScan app={app} />;
  if (!columns) return <NeedsDatabase view="Data quality" needs="a database to profile" />;

  const flagged = columns.filter((c) => c.metrics.some((m) => m.anomalous));
  const shown = sp.all ? columns : flagged;
  const tables = [...new Set(shown.map((c) => c.table))];
  const scanId = ctx.scan.scan_id;
  const tableCount = new Set(columns.map((c) => c.table)).size;

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-3 gap-4">
        {[["Columns profiled", columns.length, "text-ink"], ["Outside their learned range", flagged.length, flagged.length ? "text-red-600 dark:text-red-400" : "text-emerald-600 dark:text-emerald-400"], ["Tables", tableCount, "text-ink"]].map(([label, value, tone]) => (
          <div key={String(label)} className="rounded-xl border border-line bg-surface p-4 shadow-card">
            <div className="text-xs font-medium uppercase tracking-wide text-muted">{label}</div>
            <div className={`mt-2 text-3xl font-semibold tabular-nums tracking-tight ${tone}`}>{value}</div>
          </div>
        ))}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-3xl text-sm text-muted">
          Each value is drawn against the range learned from that column&apos;s own history. The shaded band is the widest of the three detectors&apos; ranges and the thin bars are the detectors individually. A red dot is outside the range.
        </p>
        <Link href={sp.all ? `/${app}/data-quality?scan=${scanId}` : `/${app}/data-quality?scan=${scanId}&all=1`} className="rounded-lg border border-line-strong bg-surface px-3 py-1.5 text-sm text-ink hover:bg-sunken">
          {sp.all ? `Show only flagged (${flagged.length})` : `Show all ${columns.length} columns`}
        </Link>
      </div>

      {tables.length === 0 && <EmptyState icon="check" title="Every column is inside its learned range">Nothing in the current window departs from the history.</EmptyState>}

      {tables.map((table) => (
        <Card key={table} title={table} note={`${shown.filter((c) => c.table === table).length} columns`} padded={false}>
          <div className="divide-y divide-line">
            {shown.filter((c) => c.table === table).map((c) => (
              <div key={c.column} className="p-5">
                <div className="mb-3 flex flex-wrap items-baseline gap-x-4 gap-y-1">
                  <span className="font-mono text-sm font-semibold text-ink">{c.column}</span>
                  <span className="text-xs text-muted">{c.rows} rows · {c.distinct} distinct · NULL {pct(c.null_rate)} · duplicates {pct(c.duplicate_rate)}</span>
                </div>
                <div className="grid gap-3 md:grid-cols-3">
                  {c.metrics.map((m) => (
                    <div key={m.metric} className={`rounded-lg p-3 ring-1 ring-inset ${m.anomalous ? "bg-red-50 ring-red-200 dark:bg-red-500/10 dark:ring-red-500/30" : "bg-sunken ring-line"}`}>
                      <div className="flex items-baseline justify-between text-sm">
                        <span className="font-medium text-ink">{LABEL[m.metric]}</span>
                        <span className="tabular-nums font-semibold text-ink">{pct(m.observation)}</span>
                      </div>
                      <div className="my-1.5"><RangeBar value={m.observation} detections={m.detections} anomalous={m.anomalous} /></div>
                      <div className="text-xs text-muted">{m.fired} of {m.evaluated} detectors outside their range{m.direction && m.anomalous ? ` (${m.direction})` : ""}</div>
                      {m.metric === "distribution_shift" && m.anomalous && m.explanation.categories && (
                        <ul className="mt-2 space-y-0.5 text-xs text-muted">
                          {m.explanation.categories.slice(0, 3).map((cat) => (
                            <li key={cat.value}><code className="font-mono">{cat.value}</code>: {pct(cat.baselineShare)} to <b className="text-ink">{pct(cat.currentShare)}</b></li>
                          ))}
                        </ul>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </Card>
      ))}
    </div>
  );
}

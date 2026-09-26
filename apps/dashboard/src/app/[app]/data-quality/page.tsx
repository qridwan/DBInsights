import Link from "next/link";
import { ApiProblem, NoScan, NeedsDatabase } from "@/components/Page";
import { RangeBar } from "@/components/RangeBar";
import { api, resolveScan, type ColumnQuality, type ScanRow } from "@/lib/api";
import { pct } from "@/lib/ui";

export const dynamic = "force-dynamic";

const LABEL = { null_rate: "NULL rate", duplicate_rate: "Duplicate rate", distribution_shift: "Distribution shift" } as const;

export default async function DataQuality({ params, searchParams }: { params: Promise<{ app: string }>; searchParams: Promise<{ scan?: string; all?: string }> }) {
  const { app } = await params;
  const sp = await searchParams;
  let scan: ScanRow | null;
  let columns: ColumnQuality[] | null = [];
  try {
    scan = await resolveScan(app, sp.scan);
    if (scan) columns = await api.dataQuality(scan.scan_id);
  } catch (error) {
    return <ApiProblem error={error} />;
  }
  if (!scan) return <NoScan app={app} />;
  if (!columns) return <NeedsDatabase view="Data quality" needs="a database to profile" />;

  const flagged = columns.filter((c) => c.metrics.some((m) => m.anomalous));
  const shown = sp.all ? columns : flagged;
  const tables = [...new Set(shown.map((c) => c.table))];
  const scanQuery = `scan=${scan.scan_id}`;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-2xl text-sm text-slate-600">
          Each value is drawn against the range learned from that column&apos;s own history (the shaded band is the widest of the
          three detectors&apos; ranges; the thin bars are the detectors individually). A red dot is outside the range.
        </p>
        <Link href={sp.all ? `/${app}/data-quality?${scanQuery}` : `/${app}/data-quality?${scanQuery}&all=1`} className="rounded-md border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-50">
          {sp.all ? `Only flagged (${flagged.length})` : `Show all ${columns.length} columns`}
        </Link>
      </div>

      {tables.length === 0 && <div className="rounded-lg border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500">No column is outside its learned range.</div>}

      {tables.map((table) => (
        <section key={table} className="rounded-lg border border-slate-200 bg-white shadow-sm">
          <h2 className="border-b border-slate-100 px-4 py-2 text-sm font-semibold">{table}</h2>
          <div className="divide-y divide-slate-100">
            {shown.filter((c) => c.table === table).map((c) => (
              <div key={c.column} className="p-4">
                <div className="mb-2 flex flex-wrap items-baseline gap-x-4 gap-y-1">
                  <span className="font-mono text-sm font-medium">{c.column}</span>
                  <span className="text-xs text-slate-500">
                    {c.rows} rows · {c.distinct} distinct · NULL {pct(c.null_rate)} · duplicates {pct(c.duplicate_rate)}
                  </span>
                </div>
                <div className="grid gap-4 md:grid-cols-3">
                  {c.metrics.map((m) => (
                    <div key={m.metric} className={`rounded-md p-3 ${m.anomalous ? "bg-red-50 ring-1 ring-red-200" : "bg-slate-50"}`}>
                      <div className="flex items-baseline justify-between text-sm">
                        <span className="font-medium">{LABEL[m.metric]}</span>
                        <span className="tabular-nums">{pct(m.observation)}</span>
                      </div>
                      <RangeBar value={m.observation} detections={m.detections} anomalous={m.anomalous} />
                      <div className="mt-1 text-xs text-slate-500">
                        {m.fired} of {m.evaluated} detectors outside their range{m.direction && m.anomalous ? ` (${m.direction})` : ""}
                      </div>
                      {m.metric === "distribution_shift" && m.anomalous && m.explanation.categories && (
                        <ul className="mt-2 space-y-0.5 text-xs text-slate-600">
                          {m.explanation.categories.slice(0, 3).map((cat) => (
                            <li key={cat.value}>
                              <code>{cat.value}</code>: {pct(cat.baselineShare)} &rarr; <b>{pct(cat.currentShare)}</b>
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}

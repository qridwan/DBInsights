import { Card } from "@/components/ui/Card";
import { Icon } from "@/components/ui/icons";
import { ApiProblem, NoScan } from "@/components/ui/State";
import { api, type SchemaView } from "@/lib/api";
import { loadScan, type ScanContext } from "@/lib/scans";

export const dynamic = "force-dynamic";

const key = (table: string, columns: string[]) => `${table}|${columns.join(",")}`;

export default async function Schema({ params, searchParams }: { params: Promise<{ app: string }>; searchParams: Promise<{ scan?: string }> }) {
  const { app } = await params;
  const { scan: scanParam } = await searchParams;
  let ctx: ScanContext | null;
  let view: SchemaView | null = null;
  try {
    ctx = await loadScan(app, scanParam);
    if (ctx) view = await api.schema(ctx.scan.scan_id);
  } catch (error) {
    return <ApiProblem error={error} />;
  }
  if (!ctx || !view) return <NoScan app={app} />;

  const d = view.divergence;
  const actual = view.actual;
  const notApplied = new Set((d?.declared_indexes_not_applied ?? []).map((i) => key(i.table, i.columns)));
  const notDeclared = new Set((d?.indexes_not_declared ?? []).map((i) => key(i.table, i.columns)));
  const summary: [string, number][] = !d ? [] : [
    ["In the database, not in schema.prisma", d.indexes_not_declared.length],
    ["In schema.prisma, not in the database", d.declared_indexes_not_applied.length],
    ["Column type or nullability mismatches", d.column_mismatches.length],
    ["Foreign keys not applied", d.foreign_keys_not_applied.length],
    ["Foreign keys not declared", d.foreign_keys_not_declared.length],
  ];

  return (
    <div className="space-y-6">
      {!actual ? (
        <div className="flex gap-3 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-200">
          <Icon name="info" className="mt-0.5 h-5 w-5 shrink-0" />
          <p>Only the declared schema is shown. There is no database to read, so the actual schema and the divergence between the two are not available for a scanned project. Findings about missing indexes assume the declared indexes are the whole truth.</p>
        </div>
      ) : (
        <p className="max-w-3xl text-sm text-muted">The declared schema (<code className="font-mono text-xs">schema.prisma</code>) and the actual schema (the live database catalog) are separate evidence sources. They are shown side by side and never merged: their divergence is the measurement.</p>
      )}

      {d && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          {summary.map(([label, n]) => (
            <div key={label} className={`rounded-xl border p-4 shadow-card ${n ? "border-amber-300 bg-amber-50 dark:border-amber-500/30 dark:bg-amber-500/10" : "border-line bg-surface"}`}>
              <div className={`text-3xl font-semibold tabular-nums tracking-tight ${n ? "text-amber-700 dark:text-amber-300" : "text-ink"}`}>{n}</div>
              <div className="mt-1 text-xs text-muted">{label}</div>
            </div>
          ))}
        </div>
      )}

      <div className={`grid items-start gap-6 ${actual ? "md:grid-cols-2" : ""}`}>
        <Card title="Declared: schema.prisma" note={`${view.declared.length} models`} padded={false}>
          <div className="divide-y divide-line">
            {view.declared.map((m) => (
              <div key={m.model} className="p-4">
                <div className="text-sm font-semibold text-ink">{m.model} <span className="font-normal text-faint">maps to {m.table}</span></div>
                <div className="mt-2 flex flex-wrap gap-1">
                  {m.fields.map((f) => <span key={f.name} className="rounded bg-indigo-50 px-1.5 py-0.5 font-mono text-[11px] text-indigo-800 dark:bg-indigo-500/10 dark:text-indigo-300">{f.name}{f.optional ? "?" : ""}: {f.type}</span>)}
                </div>
                <ul className="mt-2 space-y-1">
                  {m.indexes.map((i, n) => {
                    const missing = notApplied.has(key(m.table, i.columns));
                    return (
                      <li key={n} className={`flex items-center gap-1.5 text-xs ${missing ? "font-medium text-red-600 dark:text-red-400" : "text-muted"}`}>
                        <Icon name={missing ? "alert" : "check"} className="h-3.5 w-3.5" />
                        <span className="font-mono">{i.kind}({i.columns.join(", ")})</span>{missing && <span>declared, but not in the database</span>}
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))}
          </div>
        </Card>

        {actual && (
          <Card title="Actual: the database" note={`${actual.length} tables`} padded={false}>
            <div className="divide-y divide-line">
              {actual.map((t) => (
                <div key={t.table} className="p-4">
                  <div className="text-sm font-semibold text-ink">{t.table}</div>
                  <div className="mt-2 flex flex-wrap gap-1">
                    {t.columns.map((c) => <span key={c.name} className="rounded bg-fuchsia-50 px-1.5 py-0.5 font-mono text-[11px] text-fuchsia-800 dark:bg-fuchsia-500/10 dark:text-fuchsia-300">{c.name}{c.nullable ? "?" : ""}: {c.type}</span>)}
                  </div>
                  <ul className="mt-2 space-y-1">
                    {t.indexes.map((i) => {
                      const extra = notDeclared.has(key(t.table, i.columns));
                      return (
                        <li key={i.name} className={`flex items-center gap-1.5 text-xs ${extra ? "font-medium text-red-600 dark:text-red-400" : "text-muted"}`}>
                          <Icon name={extra ? "alert" : "check"} className="h-3.5 w-3.5" />
                          <span className="font-mono">{i.kind}({i.columns.join(", ")})</span><span className="text-faint">{i.name}</span>
                          {extra && <span>in the database, not in schema.prisma</span>}
                        </li>
                      );
                    })}
                  </ul>
                </div>
              ))}
            </div>
          </Card>
        )}
      </div>
    </div>
  );
}

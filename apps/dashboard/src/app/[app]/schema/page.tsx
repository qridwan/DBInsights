import { ApiProblem, Card, NoScan } from "@/components/Page";
import { api, resolveScan, type ScanRow, type SchemaView } from "@/lib/api";

export const dynamic = "force-dynamic";

const key = (table: string, columns: string[]) => `${table}|${columns.join(",")}`;

export default async function Schema({ params, searchParams }: { params: Promise<{ app: string }>; searchParams: Promise<{ scan?: string }> }) {
  const { app } = await params;
  const { scan: scanParam } = await searchParams;
  let scan: ScanRow | null;
  let view: SchemaView | null = null;
  try {
    scan = await resolveScan(app, scanParam);
    if (scan) view = await api.schema(scan.scan_id);
  } catch (error) {
    return <ApiProblem error={error} />;
  }
  if (!scan || !view) return <NoScan app={app} />;

  const d = view.divergence;
  const notApplied = new Set(d.declared_indexes_not_applied.map((i) => key(i.table, i.columns)));
  const notDeclared = new Set(d.indexes_not_declared.map((i) => key(i.table, i.columns)));
  const summary: [string, number][] = [
    ["Indexes in the database, not in schema.prisma", d.indexes_not_declared.length],
    ["Indexes in schema.prisma, not in the database", d.declared_indexes_not_applied.length],
    ["Column type / nullability mismatches", d.column_mismatches.length],
    ["Foreign keys not applied", d.foreign_keys_not_applied.length],
    ["Foreign keys not declared", d.foreign_keys_not_declared.length],
  ];

  return (
    <div className="space-y-5">
      <p className="text-sm text-slate-600">
        The declared schema (schema.prisma) and the actual schema (the live database catalog) are separate evidence sources, shown side by
        side and never merged. Their divergence is the measurement.
      </p>
      <div className="grid gap-3 sm:grid-cols-5">
        {summary.map(([label, n]) => (
          <div key={label} className={`rounded-lg border p-3 ${n ? "border-amber-300 bg-amber-50" : "border-slate-200 bg-white"}`}>
            <div className="text-2xl font-semibold tabular-nums">{n}</div>
            <div className="text-xs text-slate-600">{label}</div>
          </div>
        ))}
      </div>

      <div className="grid gap-5 md:grid-cols-2">
        <Card title="Declared: schema.prisma" note={`${view.declared.length} models`}>
          <div className="space-y-4">
            {view.declared.map((m) => (
              <div key={m.model}>
                <div className="text-sm font-semibold">{m.model} <span className="font-normal text-slate-400">→ {m.table}</span></div>
                <div className="mt-1 flex flex-wrap gap-1">
                  {m.fields.map((f) => <span key={f.name} className="rounded bg-indigo-50 px-1.5 py-0.5 font-mono text-[11px] text-indigo-800">{f.name}{f.optional ? "?" : ""}: {f.type}</span>)}
                </div>
                <ul className="mt-1 space-y-0.5">
                  {m.indexes.map((i, n) => {
                    const missing = notApplied.has(key(m.table, i.columns));
                    return (
                      <li key={n} className={`text-xs ${missing ? "font-medium text-red-700" : "text-slate-600"}`}>
                        {i.kind}({i.columns.join(", ")}){missing ? "  ← declared, but not in the database" : ""}
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))}
          </div>
        </Card>

        <Card title="Actual: the database" note={`${view.actual.length} tables`}>
          <div className="space-y-4">
            {view.actual.map((t) => (
              <div key={t.table}>
                <div className="text-sm font-semibold">{t.table}</div>
                <div className="mt-1 flex flex-wrap gap-1">
                  {t.columns.map((c) => <span key={c.name} className="rounded bg-fuchsia-50 px-1.5 py-0.5 font-mono text-[11px] text-fuchsia-800">{c.name}{c.nullable ? "?" : ""}: {c.type}</span>)}
                </div>
                <ul className="mt-1 space-y-0.5">
                  {t.indexes.map((i) => {
                    const extra = notDeclared.has(key(t.table, i.columns));
                    return (
                      <li key={i.name} className={`text-xs ${extra ? "font-medium text-red-700" : "text-slate-600"}`}>
                        {i.kind}({i.columns.join(", ")}) <span className="text-slate-400">{i.name}</span>{extra ? "  ← in the database, not in schema.prisma" : ""}
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}

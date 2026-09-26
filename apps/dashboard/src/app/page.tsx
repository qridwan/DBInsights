import Link from "next/link";
import { NewScanButton } from "@/components/shell/NewScanButton";
import { PageHeader } from "@/components/ui/Card";
import { SeverityBadge } from "@/components/ui/Badge";
import { EmptyState, ApiProblem } from "@/components/ui/State";
import { Icon } from "@/components/ui/icons";
import { Sparkline } from "@/components/ui/Sparkline";
import { api, type AppRow, type ScanRow } from "@/lib/api";
import { timeAgo } from "@/lib/ui";

export const dynamic = "force-dynamic";

interface Entry { row: AppRow; scans: ScanRow[] }

function SeverityBar({ high, medium, low }: { high: number; medium: number; low: number }) {
  const total = high + medium + low;
  if (!total) return <div className="h-1.5 rounded-full bg-emerald-500/30" />;
  return (
    <div className="flex h-1.5 overflow-hidden rounded-full bg-sunken" role="img" aria-label={`${high} high, ${medium} medium, ${low} low`}>
      <div className="bg-red-500" style={{ width: `${(high / total) * 100}%` }} />
      <div className="bg-amber-500" style={{ width: `${(medium / total) * 100}%` }} />
      <div className="bg-slate-400" style={{ width: `${(low / total) * 100}%` }} />
    </div>
  );
}

function Card({ entry }: { entry: Entry }) {
  const { row, scans } = entry;
  const ok = scans.filter((s) => s.status === "ok");
  const latest = ok[0];
  const previous = ok[1];
  const delta = latest && previous ? latest.total - previous.total : null;
  return (
    <Link href={`/${row.app}`} className="group block rounded-xl border border-line bg-surface p-5 shadow-card transition hover:border-line-strong hover:shadow-md">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate text-base font-semibold text-ink group-hover:text-brand">{row.app}</div>
          <div className="mt-0.5 flex items-center gap-1.5 text-xs text-muted">
            <Icon name={row.kind === "project" ? (row.source?.kind === "git" ? "git" : "folder") : "database"} className="h-3.5 w-3.5" />
            {row.kind === "project" ? "Scanned project" : "Test application"}
          </div>
        </div>
        {ok.length > 1 && <Sparkline values={ok.slice().reverse().map((s) => s.total)} color="var(--faint)" />}
      </div>
      {latest ? (
        <>
          <div className="mt-4 flex items-end justify-between">
            <div>
              <span className="text-3xl font-semibold tabular-nums tracking-tight text-ink">{latest.total}</span>
              <span className="ml-1.5 text-sm text-muted">findings</span>
            </div>
            {delta !== null && delta !== 0 && (
              <span className={`inline-flex items-center gap-0.5 text-xs font-medium ${delta < 0 ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400"}`}>
                <Icon name={delta > 0 ? "arrowUp" : "arrowDown"} className="h-3 w-3" />{Math.abs(delta)}
              </span>
            )}
          </div>
          <div className="mt-3"><SeverityBar high={latest.high} medium={latest.medium} low={latest.low} /></div>
          <div className="mt-3 flex items-center gap-3 text-xs text-muted">
            <span className="inline-flex items-center gap-1.5"><SeverityBadge level="HIGH" /> <b className="tabular-nums text-ink">{latest.high}</b></span>
            <span className="inline-flex items-center gap-1.5"><SeverityBadge level="MEDIUM" /> <b className="tabular-nums text-ink">{latest.medium}</b></span>
            <span className="ml-auto inline-flex items-center gap-1"><Icon name="clock" className="h-3 w-3" />{timeAgo(latest.started_at)}</span>
          </div>
        </>
      ) : (
        <p className="mt-6 text-sm text-muted">Not scanned yet. Open it and press Run scan.</p>
      )}
    </Link>
  );
}

export default async function Home() {
  let entries: Entry[];
  try {
    const rows = await api.apps();
    entries = await Promise.all(rows.map(async (row) => ({ row, scans: await api.scans(row.app).catch(() => []) })));
  } catch (error) {
    return <ApiProblem error={error} />;
  }
  const latest = entries.map((e) => e.scans.find((s) => s.status === "ok")).filter((s): s is ScanRow => Boolean(s));
  const totals = { findings: latest.reduce((n, s) => n + s.total, 0), high: latest.reduce((n, s) => n + s.high, 0), scanned: latest.length };
  const builtIn = entries.filter((e) => e.row.kind === "app");
  const projects = entries.filter((e) => e.row.kind === "project");

  return (
    <div className="space-y-8">
      <PageHeader
        title="Overview"
        description="Every application and project in one place: what the analyzer found, and how it changed since the last scan."
        actions={<NewScanButton />}
      />

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {[
          ["Applications and projects", entries.length, "text-ink"],
          ["Scanned", totals.scanned, "text-ink"],
          ["Open findings", totals.findings, "text-ink"],
          ["High severity", totals.high, totals.high ? "text-red-600 dark:text-red-400" : "text-emerald-600 dark:text-emerald-400"],
        ].map(([label, value, tone]) => (
          <div key={String(label)} className="rounded-xl border border-line bg-surface p-4 shadow-card">
            <div className="text-xs font-medium uppercase tracking-wide text-muted">{label}</div>
            <div className={`mt-2 text-3xl font-semibold tabular-nums tracking-tight ${tone}`}>{value}</div>
          </div>
        ))}
      </div>

      <section className="space-y-3">
        <div className="flex items-baseline justify-between">
          <h2 className="text-sm font-semibold text-ink">Test applications</h2>
          <span className="text-xs text-muted">Run with a database, so every evidence layer is available</span>
        </div>
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">{builtIn.map((e) => <Card key={e.row.app} entry={e} />)}</div>
      </section>

      <section className="space-y-3">
        <div className="flex items-baseline justify-between">
          <h2 className="text-sm font-semibold text-ink">Scanned projects</h2>
          <span className="text-xs text-muted">Real-world projects, analyzed without a database</span>
        </div>
        {projects.length > 0 ? (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">{projects.map((e) => <Card key={e.row.app} entry={e} />)}</div>
        ) : (
          <EmptyState icon="git" title="No projects scanned yet" action={<NewScanButton label="Scan your first project" variant="quiet" />}>
            Point it at any Prisma project by Git URL or local folder. It runs the analysis that needs no database.
          </EmptyState>
        )}
      </section>
    </div>
  );
}

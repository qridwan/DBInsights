import { unstable_rethrow } from "next/navigation";
import Link from "next/link";
import { FindingView } from "@/components/FindingView";
import { ConfidenceMeter, LayerChip, NewBadge, RuleTag, SeverityBadge } from "@/components/ui/Badge";
import { EmptyState, ApiProblem, NoScan } from "@/components/ui/State";
import { Icon } from "@/components/ui/icons";
import { api, type Finding, type Level } from "@/lib/api";
import { diffFindings, loadScan, type ScanContext } from "@/lib/scans";
import { LAYERS, RULES } from "@/lib/ui";

export const dynamic = "force-dynamic";

type Search = { scan?: string; severity?: string; confidence?: string; rule?: string; layer?: string; q?: string; only?: string; f?: string };

const STRIPE: Record<Level, string> = { HIGH: "bg-red-500", MEDIUM: "bg-amber-500", LOW: "bg-slate-300 dark:bg-slate-600" };

function Chips({ label, param, options, current, href }: { label: string; param: string; options: { value: string; label: string }[]; current?: string; href: (o: Record<string, string | undefined>) => string }) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs font-medium text-muted">{label}</span>
      <div className="flex rounded-lg bg-sunken p-0.5 text-xs">
        {[{ value: "", label: "All" }, ...options].map((o) => {
          const active = (current ?? "") === o.value;
          return (
            <Link key={o.value} href={href({ [param]: o.value || undefined, f: undefined })} aria-current={active ? "true" : undefined}
              className={`rounded-md px-2.5 py-1 ${active ? "bg-surface font-medium text-ink shadow-card" : "text-muted hover:text-ink"}`}>
              {o.label}
            </Link>
          );
        })}
      </div>
    </div>
  );
}

export default async function Findings({ params, searchParams }: { params: Promise<{ app: string }>; searchParams: Promise<Search> }) {
  const { app } = await params;
  const sp = await searchParams;
  let ctx: ScanContext | null;
  let all: Finding[] = [];
  let before: Finding[] | null = null;
  try {
    ctx = await loadScan(app, sp.scan);
    if (ctx) {
      [all, before] = await Promise.all([
        api.findings(ctx.scan.scan_id, { severity: sp.severity, confidence: sp.confidence, rule: sp.rule, layer: sp.layer }),
        ctx.previous ? api.findings(ctx.previous.scan_id) : Promise.resolve(null),
      ]);
    }
  } catch (error) {
    unstable_rethrow(error);
    return <ApiProblem error={error} />;
  }
  if (!ctx) return <NoScan app={app} />;

  const { added } = diffFindings(all, before);
  const q = (sp.q ?? "").trim().toLowerCase();
  const findings = all.filter((f) => (!q || `${f.title} ${f.file} ${f.rule_id}`.toLowerCase().includes(q)) && (sp.only !== "new" || added.has(f.fingerprint)));
  const selected = findings.find((f) => f.finding_id === sp.f) ?? findings[0];
  const scanId = ctx.scan.scan_id;

  const href = (overrides: Record<string, string | undefined>) => {
    const next = { ...sp, scan: scanId, ...overrides };
    const query = new URLSearchParams(Object.entries(next).filter((e): e is [string, string] => Boolean(e[1]))).toString();
    return `/${app}/findings${query ? `?${query}` : ""}`;
  };
  const filtered = Boolean(sp.severity || sp.confidence || sp.rule || sp.layer || q || sp.only);
  const levels = ["HIGH", "MEDIUM", "LOW"].map((v) => ({ value: v.toLowerCase(), label: v.charAt(0) + v.slice(1).toLowerCase() }));

  return (
    <div className="space-y-4">
      <form method="get" className="flex flex-wrap items-center gap-x-5 gap-y-3 rounded-xl border border-line bg-surface p-3 shadow-card">
        <input type="hidden" name="scan" value={scanId} />
        {sp.severity && <input type="hidden" name="severity" value={sp.severity} />}
        {sp.confidence && <input type="hidden" name="confidence" value={sp.confidence} />}
        {sp.layer && <input type="hidden" name="layer" value={sp.layer} />}
        {sp.only && <input type="hidden" name="only" value={sp.only} />}
        <label className="relative">
          <Icon name="search" className="pointer-events-none absolute left-2.5 top-2 h-4 w-4 text-faint" />
          <input name="q" defaultValue={sp.q} placeholder="Search title, file or rule" className="w-56 rounded-lg border border-line-strong bg-surface py-1.5 pl-8 pr-3 text-sm text-ink placeholder:text-faint focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/25" />
        </label>
        <Chips label="Severity" param="severity" options={levels} current={sp.severity} href={href} />
        <Chips label="Confidence" param="confidence" options={levels} current={sp.confidence} href={href} />
        <label className="flex items-center gap-2 text-xs font-medium text-muted">Layer
          <select name="layer" defaultValue={sp.layer ?? ""} className="rounded-lg border border-line-strong bg-surface py-1.5 pl-2 pr-6 text-xs text-ink">
            <option value="">All</option>
            {LAYERS.map((l) => <option key={l.id} value={l.id}>{l.label}</option>)}
          </select>
        </label>
        <label className="flex items-center gap-2 text-xs font-medium text-muted">Rule
          <select name="rule" defaultValue={sp.rule ?? ""} className="max-w-48 rounded-lg border border-line-strong bg-surface py-1.5 pl-2 pr-6 text-xs text-ink">
            <option value="">All</option>
            {RULES.map((r) => <option key={r} value={r}>{r}</option>)}
          </select>
        </label>
        <button className="rounded-lg bg-ink px-3 py-1.5 text-xs font-medium text-canvas hover:opacity-90">Apply</button>
        {filtered && <Link href={`/${app}/findings?scan=${scanId}`} className="text-xs text-brand hover:underline">Clear filters</Link>}
        <span className="ml-auto text-sm tabular-nums text-muted">{findings.length} of {all.length} findings</span>
      </form>

      {findings.length === 0 ? (
        <EmptyState icon="filter" title="No findings match these filters" action={filtered ? <Link href={`/${app}/findings?scan=${scanId}`} className="text-sm font-medium text-brand hover:underline">Clear filters</Link> : undefined}>
          {filtered ? "Try removing a filter or changing the search." : "This scan produced no findings."}
        </EmptyState>
      ) : (
        <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
          <ul className="space-y-2 lg:max-h-[calc(100vh-15rem)] lg:overflow-y-auto lg:pr-1">
            {findings.map((f) => {
              const active = selected?.finding_id === f.finding_id;
              const body = (
                <div className={`relative overflow-hidden rounded-xl border bg-surface p-3.5 pl-5 shadow-card transition ${active ? "border-line lg:border-brand lg:ring-1 lg:ring-brand/40" : "border-line hover:border-line-strong"}`}>
                  <span className={`absolute inset-y-0 left-0 w-1 ${STRIPE[f.severity]}`} />
                  <div className="flex flex-wrap items-center gap-2">
                    <SeverityBadge level={f.severity} />
                    <ConfidenceMeter level={f.confidence} showLabel={false} />
                    {added.has(f.fingerprint) && <NewBadge />}
                    <RuleTag rule={f.rule_id} />
                  </div>
                  <div className="mt-2 text-sm font-medium leading-snug text-ink">{f.title}</div>
                  <div className="mt-1 truncate font-mono text-[11px] text-muted">{f.file}{f.line ? `:${f.line}` : ""}</div>
                  <div className="mt-2 flex flex-wrap gap-1">{f.layers.map((l) => <LayerChip key={l} layer={l} size="xs" />)}</div>
                </div>
              );
              return (
                <li key={f.finding_id}>
                  <Link href={`/${app}/findings/${f.finding_id}?scan=${scanId}`} className="block lg:hidden">{body}</Link>
                  <Link href={href({ f: f.finding_id })} scroll={false} className="hidden lg:block" aria-current={active ? "true" : undefined}>{body}</Link>
                </li>
              );
            })}
          </ul>
          <div className="hidden lg:sticky lg:top-6 lg:block lg:max-h-[calc(100vh-9rem)] lg:overflow-y-auto lg:pr-1">
            {selected && <FindingView finding={selected} scanId={scanId} ran={ctx.ran} isNew={added.has(selected.fingerprint)} compact />}
          </div>
        </div>
      )}
    </div>
  );
}

import Link from "next/link";
import { ApiProblem, NoScan } from "@/components/Page";
import { ConfidenceBadge, LayerChip, SeverityBadge } from "@/components/Badges";
import { api, resolveScan, type Finding, type ScanRow } from "@/lib/api";
import { LAYERS, RULES } from "@/lib/ui";

export const dynamic = "force-dynamic";

type Search = { scan?: string; severity?: string; confidence?: string; rule?: string; layer?: string };

function Select({ name, value, options }: { name: string; value?: string; options: { value: string; label: string }[] }) {
  return (
    <label className="text-xs text-slate-500">
      {name}
      <select name={name} defaultValue={value ?? ""} className="mt-1 block rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm text-slate-800">
        <option value="">all</option>
        {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </label>
  );
}

export default async function Findings({ params, searchParams }: { params: Promise<{ app: string }>; searchParams: Promise<Search> }) {
  const { app } = await params;
  const sp = await searchParams;
  let scan: ScanRow | null;
  let findings: Finding[] = [];
  try {
    scan = await resolveScan(app, sp.scan);
    if (scan) findings = await api.findings(scan.scan_id, { severity: sp.severity, confidence: sp.confidence, rule: sp.rule, layer: sp.layer });
  } catch (error) {
    return <ApiProblem error={error} />;
  }
  if (!scan) return <NoScan app={app} />;

  const levels = ["HIGH", "MEDIUM", "LOW"].map((v) => ({ value: v, label: v.toLowerCase() }));
  return (
    <div className="space-y-4">
      <form method="get" className="flex flex-wrap items-end gap-3 rounded-lg border border-slate-200 bg-white p-3">
        <input type="hidden" name="scan" value={scan.scan_id} />
        <Select name="severity" value={sp.severity} options={levels} />
        <Select name="confidence" value={sp.confidence} options={levels} />
        <Select name="rule" value={sp.rule} options={RULES.map((r) => ({ value: r, label: r }))} />
        <Select name="layer" value={sp.layer} options={LAYERS.map((l) => ({ value: l.id, label: l.label }))} />
        <button className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white">Filter</button>
        <Link href={`/${app}/findings?scan=${scan.scan_id}`} className="text-sm text-slate-500 underline">reset</Link>
        <span className="ml-auto text-sm text-slate-500">{findings.length} findings</span>
      </form>

      <ul className="space-y-3">
        {findings.map((f) => (
          <li key={f.finding_id}>
            <Link href={`/${app}/findings/${f.finding_id}?scan=${scan.scan_id}`} className="block rounded-lg border border-slate-200 bg-white p-4 shadow-sm hover:border-slate-400">
              <div className="flex flex-wrap items-center gap-2">
                <SeverityBadge level={f.severity} />
                <ConfidenceBadge level={f.confidence} />
                <code className="text-xs text-slate-500">{f.rule_id}</code>
              </div>
              <div className="mt-1.5 font-medium text-slate-900">{f.title}</div>
              <div className="mt-0.5 text-xs text-slate-500">{f.file}{f.line ? `:${f.line}` : ""}</div>
              <div className="mt-2 flex flex-wrap items-center gap-1.5">
                <span className="text-xs text-slate-500">evidence from</span>
                {f.layers.map((l) => <LayerChip key={l} layer={l} />)}
                <span className="text-xs text-slate-400">· {f.evidence.length} items</span>
              </div>
            </Link>
          </li>
        ))}
        {findings.length === 0 && <li className="rounded-lg border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500">No findings match these filters.</li>}
      </ul>
    </div>
  );
}

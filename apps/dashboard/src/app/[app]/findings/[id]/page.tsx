import Link from "next/link";
import { ApiProblem, Card, NoScan } from "@/components/Page";
import { ConfidenceBadge, SeverityBadge } from "@/components/Badges";
import { EvidenceChain } from "@/components/EvidenceChain";
import { Explanation } from "@/components/Explanation";
import { api, resolveScan, SCAN_LAYER_TO_SOURCE, type Finding, type Layer, type ScanRow } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function FindingPage({ params, searchParams }: { params: Promise<{ app: string; id: string }>; searchParams: Promise<{ scan?: string }> }) {
  const { app, id } = await params;
  const { scan: scanParam } = await searchParams;
  let scan: ScanRow | null;
  let finding: Finding | null = null;
  let ran: Layer[] = [];
  try {
    scan = await resolveScan(app, scanParam);
    if (scan) {
      finding = await api.finding(scan.scan_id, id).catch(() => null);
      ran = (await api.scan(scan.scan_id)).layers.map((l) => SCAN_LAYER_TO_SOURCE[l]).filter(Boolean);
    }
  } catch (error) {
    return <ApiProblem error={error} />;
  }
  if (!scan) return <NoScan app={app} />;
  if (!finding) return <p className="text-sm text-slate-600">No finding {id} in this scan.</p>;

  return (
    <div className="space-y-5">
      <Link href={`/${app}/findings?scan=${scan.scan_id}`} className="text-sm text-slate-500 hover:underline">&larr; all findings</Link>
      <div>
        <div className="flex flex-wrap items-center gap-2">
          <SeverityBadge level={finding.severity} />
          <ConfidenceBadge level={finding.confidence} />
          <code className="text-xs text-slate-500">{finding.rule_id}</code>
        </div>
        <h2 className="mt-2 text-xl font-semibold">{finding.title}</h2>
        <p className="mt-1 text-sm text-slate-500">{finding.file}{finding.line ? `:${finding.line}` : ""}</p>
      </div>

      <Card title="Evidence chain" note="each item is labelled with the layer it came from">
        <EvidenceChain evidence={finding.evidence} layers={finding.layers} ran={ran} />
      </Card>

      <Card title="What the analyzer says">
        <div className="prose prose-sm max-w-none whitespace-pre-wrap text-sm text-slate-800">{finding.body}</div>
      </Card>

      {finding.suggested_fix && (
        <Card title="Suggested fix" note="never applied automatically">
          <pre className="overflow-auto rounded bg-slate-900 p-3 text-xs text-slate-100">{finding.suggested_fix.replace(/^```\w*\n?|\n?```$/g, "")}</pre>
        </Card>
      )}

      <Explanation scan={scan.scan_id} finding={finding.finding_id} />
    </div>
  );
}

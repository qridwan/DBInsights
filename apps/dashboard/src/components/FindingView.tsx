import Link from "next/link";
import { CopyButton } from "@/components/ui/CopyButton";
import { Card } from "@/components/ui/Card";
import { ConfidenceMeter, NewBadge, RuleTag, SeverityBadge } from "@/components/ui/Badge";
import { Icon } from "@/components/ui/icons";
import { Markdown } from "@/components/ui/Markdown";
import { EvidenceChain } from "@/components/EvidenceChain";
import { Explanation } from "@/components/Explanation";
import type { Finding, Layer } from "@/lib/api";

/** One finding in full: what it is, the evidence chain behind it, the analyzer's account, the fix. */
export function FindingView({ finding, scanId, ran, isNew, compact = false }: { finding: Finding; scanId: string; ran: Layer[]; isNew?: boolean; compact?: boolean }) {
  const where = `${finding.file}${finding.line ? `:${finding.line}` : ""}`;
  const fix = finding.suggested_fix?.replace(/^```\w*\n?|\n?```$/g, "");
  return (
    <div className="space-y-5">
      <div>
        <div className="flex flex-wrap items-center gap-2">
          <SeverityBadge level={finding.severity} />
          <ConfidenceMeter level={finding.confidence} />
          <RuleTag rule={finding.rule_id} />
          {isNew && <NewBadge />}
          <span className="ml-auto text-xs text-faint">{finding.finding_id}</span>
        </div>
        <h2 className={`mt-3 font-semibold tracking-tight text-ink ${compact ? "text-base" : "text-xl"}`}>{finding.title}</h2>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <code className="break-all rounded-md bg-sunken px-2 py-1 font-mono text-xs text-muted">{where}</code>
          <CopyButton text={where} label="Copy location" />
          {compact && (
            <Link href={`findings/${finding.finding_id}?scan=${scanId}`} className="inline-flex items-center gap-1 text-xs text-brand hover:underline">
              Open full page <Icon name="external" className="h-3 w-3" />
            </Link>
          )}
        </div>
      </div>

      <Card title="Evidence chain" note="Each item is labelled with the layer it came from.">
        <EvidenceChain evidence={finding.evidence} layers={finding.layers} ran={ran} />
      </Card>

      <Card title="What the analyzer found">
        <Markdown text={finding.body} />
      </Card>

      {fix && (
        <Card title="Suggested fix" note="Never applied automatically." action={<CopyButton text={fix} />}>
          <pre className="overflow-auto rounded-lg bg-[#0f1420] p-4 font-mono text-xs leading-relaxed text-slate-200">{fix}</pre>
        </Card>
      )}

      <Explanation scan={scanId} finding={finding.finding_id} />
    </div>
  );
}

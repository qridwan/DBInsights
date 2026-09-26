import { unstable_rethrow } from "next/navigation";
import Link from "next/link";
import { FindingView } from "@/components/FindingView";
import { Icon } from "@/components/ui/icons";
import { ApiProblem, NoScan } from "@/components/ui/State";
import { api, type Finding } from "@/lib/api";
import { diffFindings, loadScan, type ScanContext } from "@/lib/scans";

export const dynamic = "force-dynamic";

export default async function FindingPage({ params, searchParams }: { params: Promise<{ app: string; id: string }>; searchParams: Promise<{ scan?: string }> }) {
  const { app, id } = await params;
  const { scan: scanParam } = await searchParams;
  let ctx: ScanContext | null;
  let finding: Finding | null = null;
  let isNew = false;
  try {
    ctx = await loadScan(app, scanParam);
    if (ctx) {
      finding = await api.finding(ctx.scan.scan_id, id).catch(() => null);
      if (finding && ctx.previous) {
        const [now, before] = await Promise.all([api.findings(ctx.scan.scan_id), api.findings(ctx.previous.scan_id)]);
        isNew = diffFindings(now, before).added.has(finding.fingerprint);
      }
    }
  } catch (error) {
    unstable_rethrow(error);
    return <ApiProblem error={error} />;
  }
  if (!ctx) return <NoScan app={app} />;
  if (!finding) return <p className="text-sm text-muted">There is no finding {id} in this scan.</p>;

  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <nav className="flex items-center gap-1.5 text-sm text-muted" aria-label="Breadcrumb">
        <Link href={`/${app}/findings?scan=${ctx.scan.scan_id}`} className="hover:text-ink">Findings</Link>
        <Icon name="chevronRight" className="h-3.5 w-3.5" />
        <span className="text-ink">{finding.finding_id}</span>
      </nav>
      <FindingView finding={finding} scanId={ctx.scan.scan_id} ran={ctx.ran} isNew={isNew} />
    </div>
  );
}

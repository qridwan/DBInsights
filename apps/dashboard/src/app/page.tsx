import Link from "next/link";
import { ApiProblem } from "@/components/Page";
import { SeverityBadge } from "@/components/Badges";
import { ScanProject } from "@/components/ScanProject";
import { api, type AppRow } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function Home() {
  let apps: AppRow[];
  try {
    apps = await api.apps();
  } catch (error) {
    return <ApiProblem error={error} />;
  }
  const card = ({ app, latest_scan: scan, kind }: AppRow) => (
    <Link key={app} href={`/${app}`} className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm hover:border-slate-400">
      <div className="text-lg font-medium">{app}</div>
      {scan ? (
        <div className="mt-3 flex items-center gap-2 text-sm">
          <span className="text-slate-600">{scan.total} findings</span>
          <SeverityBadge level="HIGH" /> {scan.high}
          <SeverityBadge level="MEDIUM" /> {scan.medium}
          <span className="ml-auto text-xs text-slate-400">{new Date(scan.started_at).toLocaleString()}</span>
        </div>
      ) : (
        <div className="mt-3 text-sm text-slate-500">{kind === "app" ? "Not scanned yet" : "No scan"}</div>
      )}
    </Link>
  );
  const builtIn = apps.filter((a) => a.kind === "app");
  const scanned = apps.filter((a) => a.kind === "project");
  return (
    <div className="space-y-8">
      <section className="space-y-4">
        <h1 className="text-xl font-semibold">Test applications</h1>
        <p className="text-sm text-slate-600">Run here with a database, so every layer is available.</p>
        <div className="grid gap-4 sm:grid-cols-2">{builtIn.map(card)}</div>
      </section>
      <section className="space-y-4">
        <h1 className="text-xl font-semibold">Scanned projects</h1>
        {scanned.length > 0 && <div className="grid gap-4 sm:grid-cols-2">{scanned.map(card)}</div>}
        <ScanProject />
      </section>
    </div>
  );
}

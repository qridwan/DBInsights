import { notFound } from "next/navigation";
import { Suspense } from "react";
import { RemoveProject } from "@/components/RemoveProject";
import { RunScan } from "@/components/ScanControls";
import { Tabs } from "@/components/shell/Tabs";
import { ScanPickerClient as ScanPickerBridge } from "@/components/shell/ScanPickerClient";
import { Icon } from "@/components/ui/icons";
import { api, type ScanRow } from "@/lib/api";
import { timeAgo } from "@/lib/ui";

export default async function AppLayout({ children, params }: { children: React.ReactNode; params: Promise<{ app: string }> }) {
  const { app } = await params;
  // Anything that is not an application (a favicon request, a typo) is a 404, not an API error.
  const apps = await api.apps().catch(() => null);
  if (apps && !apps.some((a) => a.app === app)) notFound();
  const entry = apps?.find((a) => a.app === app);
  const project = entry?.kind === "project";
  const scans: ScanRow[] = await api.scans(app).catch(() => []);
  const ok = scans.filter((s) => s.status === "ok");
  const latest = ok[0];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2.5">
            <h1 className="truncate text-2xl font-semibold tracking-tight text-ink">{app}</h1>
            <span className="rounded-full bg-sunken px-2 py-0.5 text-[11px] font-medium text-muted ring-1 ring-inset ring-line">{project ? "Scanned project" : "Test application"}</span>
          </div>
          <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted">
            {project && entry?.source && (
              <span className="inline-flex items-center gap-1 break-all"><Icon name={entry.source.kind === "git" ? "git" : "folder"} className="h-3.5 w-3.5" />{entry.source.origin}</span>
            )}
            {latest && <span className="inline-flex items-center gap-1"><Icon name="clock" className="h-3.5 w-3.5" />Last scanned {timeAgo(latest.started_at)}</span>}
            {!latest && <span>Not scanned yet</span>}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          {latest && <Suspense fallback={null}><ScanPickerBridge scans={ok} /></Suspense>}
          {project && <RemoveProject name={app} />}
          <RunScan app={app} project={project} />
        </div>
      </div>
      <div className="border-b border-line">
        <Suspense fallback={<div className="h-11" />}><Tabs app={app} project={project} /></Suspense>
      </div>
      <div className="fade-in">{children}</div>
    </div>
  );
}


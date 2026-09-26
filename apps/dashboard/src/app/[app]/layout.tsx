import { notFound } from "next/navigation";
import { Suspense } from "react";
import { AppNav } from "@/components/AppNav";
import { RunScan } from "@/components/ScanControls";
import { api } from "@/lib/api";

export default async function AppLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ app: string }>;
}) {
  const { app } = await params;
  // Anything that is not an application (a favicon request, a typo) is a 404, not an API error.
  const apps = await api.apps().catch(() => null);
  if (apps && !apps.some((a) => a.app === app)) notFound();
  const project = apps?.find((a) => a.app === app)?.kind === "project";
  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h1 className="text-xl font-semibold">{app}</h1>
          {project && <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600 ring-1 ring-inset ring-slate-300">scanned project</span>}
        </div>
        <RunScan app={app} project={project} />
      </div>
      <Suspense fallback={null}>
        <AppNav app={app} project={project} />
      </Suspense>
      {children}
    </div>
  );
}

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
  const known = await api.apps().then((apps) => apps.map((a) => a.app)).catch(() => null);
  if (known && !known.includes(app)) notFound();
  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">{app}</h1>
        <RunScan app={app} />
      </div>
      <Suspense fallback={null}>
        <AppNav app={app} />
      </Suspense>
      {children}
    </div>
  );
}

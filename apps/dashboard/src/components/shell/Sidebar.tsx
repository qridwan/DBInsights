"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { Brand } from "./Brand";
import { ThemeToggle } from "./ThemeToggle";
import { Icon } from "@/components/ui/icons";
import { ScanDialogContext } from "./ScanDialogContext";
import { ScanProjectDialog } from "@/components/ScanProject";

export interface NavItem {
  app: string;
  kind: "app" | "project";
  status: "high" | "medium" | "clean" | "none";
  total: number | null;
}

const DOT = { high: "bg-red-500", medium: "bg-amber-500", clean: "bg-emerald-500", none: "bg-line-strong" };
const DOT_LABEL = { high: "has high-severity findings", medium: "has medium-severity findings", clean: "no findings", none: "not scanned yet" };

function Group({ title, items, path }: { title: string; items: NavItem[]; path: string }) {
  if (items.length === 0) return null;
  return (
    <div>
      <div className="px-3 pb-1.5 text-[11px] font-medium uppercase tracking-wider text-faint">{title}</div>
      <ul className="space-y-0.5">
        {items.map((item) => {
          const active = path === `/${item.app}` || path.startsWith(`/${item.app}/`);
          return (
            <li key={item.app}>
              <Link
                href={`/${item.app}`}
                aria-current={active ? "page" : undefined}
                className={`group flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm ${active ? "bg-brand-soft font-medium text-brand" : "text-muted hover:bg-sunken hover:text-ink"}`}
              >
                <span className={`h-2 w-2 shrink-0 rounded-full ${DOT[item.status]}`} title={DOT_LABEL[item.status]} />
                <span className="truncate">{item.app}</span>
                {item.total !== null && <span className="ml-auto text-xs tabular-nums text-faint">{item.total}</span>}
              </Link>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function Content({ items, apiOk, onNewProject }: { items: NavItem[]; apiOk: boolean; onNewProject: () => void }) {
  const path = usePathname();
  return (
    <div className="flex h-full flex-col">
      <div className="px-4 py-5"><Link href="/" aria-label="Overview"><Brand /></Link></div>
      <nav className="flex-1 space-y-6 overflow-y-auto px-3 pb-4" aria-label="Applications">
        <Link href="/" aria-current={path === "/" ? "page" : undefined} className={`flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm ${path === "/" ? "bg-brand-soft font-medium text-brand" : "text-muted hover:bg-sunken hover:text-ink"}`}>
          <Icon name="home" /> Overview
        </Link>
        <Group title="Test applications" items={items.filter((i) => i.kind === "app")} path={path} />
        <Group title="Scanned projects" items={items.filter((i) => i.kind === "project")} path={path} />
      </nav>
      <div className="space-y-3 border-t border-line p-3">
        <button onClick={onNewProject} className="flex w-full items-center justify-center gap-2 rounded-lg bg-brand px-3 py-2 text-sm font-medium text-brand-ink hover:opacity-90">
          <Icon name="plus" /> Scan a project
        </button>
        <div className="flex items-center justify-between px-1">
          <span className="flex items-center gap-2 text-xs text-muted" title={apiOk ? "Dashboard API reachable" : "Cannot reach the dashboard API"}>
            <span className={`h-2 w-2 rounded-full ${apiOk ? "bg-emerald-500" : "bg-red-500"}`} />
            API {apiOk ? "connected" : "unreachable"}
          </span>
          <ThemeToggle />
        </div>
      </div>
    </div>
  );
}

/** Persistent sidebar on desktop, a slide-in drawer on small screens. */
export function Shell({ items, apiOk, children }: { items: NavItem[]; apiOk: boolean; children: React.ReactNode }) {
  const path = usePathname();
  const [drawer, setDrawer] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  useEffect(() => setDrawer(false), [path]);
  return (
    <ScanDialogContext.Provider value={{ open: () => setDialogOpen(true) }}>
    <div className="min-h-screen lg:pl-64">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 border-r border-line bg-surface lg:block">
        <Content items={items} apiOk={apiOk} onNewProject={() => setDialogOpen(true)} />
      </aside>

      <header className="sticky top-0 z-20 flex items-center justify-between border-b border-line bg-surface/90 px-4 py-2.5 backdrop-blur lg:hidden">
        <Link href="/"><Brand compact /></Link>
        <button onClick={() => setDrawer(true)} className="rounded-md p-2 text-muted hover:bg-sunken" aria-label="Open navigation"><Icon name="menu" className="h-5 w-5" /></button>
      </header>
      {drawer && (
        <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true" aria-label="Navigation">
          <div className="absolute inset-0 bg-black/40" onClick={() => setDrawer(false)} />
          <div className="absolute inset-y-0 left-0 w-72 max-w-[85vw] border-r border-line bg-surface shadow-xl">
            <Content items={items} apiOk={apiOk} onNewProject={() => { setDrawer(false); setDialogOpen(true); }} />
          </div>
        </div>
      )}

      <main className="mx-auto w-full max-w-[1400px] px-4 py-6 sm:px-6 lg:px-8 lg:py-8">{children}</main>
      <ScanProjectDialog open={dialogOpen} onClose={() => setDialogOpen(false)} />
    </div>
    </ScanDialogContext.Provider>
  );
}

"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { Icon, type IconName } from "@/components/ui/icons";

const TABS: { href: string; label: string; icon: IconName; needsDatabase?: boolean }[] = [
  { href: "", label: "Overview", icon: "activity" },
  { href: "/findings", label: "Findings", icon: "bug" },
  { href: "/queries", label: "Query analytics", icon: "code", needsDatabase: true },
  { href: "/data-quality", label: "Data quality", icon: "table", needsDatabase: true },
  { href: "/schema", label: "Schema", icon: "database" },
];

/** Tabs keep the selected scan in the URL so every view describes the same scan. */
export function Tabs({ app, project = false }: { app: string; project?: boolean }) {
  const path = usePathname();
  const scan = useSearchParams().get("scan");
  return (
    <nav className="-mb-px flex gap-1 overflow-x-auto" aria-label="Sections">
      {TABS.filter((t) => !(project && t.needsDatabase)).map((tab) => {
        const href = `/${app}${tab.href}`;
        const active = tab.href === "" ? path === `/${app}` : path.startsWith(href);
        return (
          <Link
            key={tab.href}
            href={scan ? `${href}?scan=${scan}` : href}
            aria-current={active ? "page" : undefined}
            className={`flex items-center gap-2 whitespace-nowrap border-b-2 px-3.5 py-2.5 text-sm ${active ? "border-brand font-medium text-ink" : "border-transparent text-muted hover:border-line-strong hover:text-ink"}`}
          >
            <Icon name={tab.icon} className="h-4 w-4" />
            {tab.label}
          </Link>
        );
      })}
    </nav>
  );
}

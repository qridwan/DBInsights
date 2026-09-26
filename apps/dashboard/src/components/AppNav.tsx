"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";

const TABS = [
  { href: "", label: "Health" },
  { href: "/findings", label: "Findings" },
  { href: "/queries", label: "Query analytics" },
  { href: "/data-quality", label: "Data quality" },
  { href: "/schema", label: "Schema divergence" },
];

/** Tabs keep the selected scan in the URL so every view describes the same scan. */
export function AppNav({ app }: { app: string }) {
  const path = usePathname();
  const scan = useSearchParams().get("scan");
  return (
    <nav className="flex gap-1 border-b border-slate-200">
      {TABS.map((tab) => {
        const href = `/${app}${tab.href}`;
        const active = tab.href === "" ? path === `/${app}` : path.startsWith(href);
        return (
          <Link
            key={tab.href}
            href={scan ? `${href}?scan=${scan}` : href}
            className={`-mb-px border-b-2 px-3 py-2 text-sm ${
              active ? "border-slate-900 font-medium text-slate-900" : "border-transparent text-slate-500 hover:text-slate-800"
            }`}
          >
            {tab.label}
          </Link>
        );
      })}
    </nav>
  );
}

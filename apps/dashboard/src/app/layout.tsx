import type { Metadata } from "next";
import "./globals.css";
import { Shell, type NavItem } from "@/components/shell/Sidebar";
import Script from "next/script";
import { api, type AppRow } from "@/lib/api";

export const metadata: Metadata = { title: { default: "DBInsight", template: "%s · DBInsight" }, description: "Database performance and data quality, from evidence" };

// Runs before first paint so the chosen theme never flashes.
const THEME_SCRIPT = `try{var t=localStorage.getItem("dbinsight-theme");if(t==="dark"||(!t&&matchMedia("(prefers-color-scheme: dark)").matches))document.documentElement.classList.add("dark")}catch(e){}`;

function status(row: AppRow): NavItem["status"] {
  const scan = row.latest_scan;
  if (!scan) return "none";
  return scan.high > 0 ? "high" : scan.medium > 0 ? "medium" : "clean";
}

export const dynamic = "force-dynamic";

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  let apps: AppRow[] = [];
  let apiOk = true;
  try {
    apps = await api.apps();
  } catch {
    apiOk = false;
  }
  const items: NavItem[] = apps.map((a) => ({ app: a.app, kind: a.kind ?? "app", status: status(a), total: a.latest_scan ? a.latest_scan.total : null }));
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="min-h-screen">
        <Script id="theme" strategy="beforeInteractive">{THEME_SCRIPT}</Script>
        <Shell items={items} apiOk={apiOk}>{children}</Shell>
      </body>
    </html>
  );
}

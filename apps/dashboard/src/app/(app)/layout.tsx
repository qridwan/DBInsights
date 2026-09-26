import { Shell, type NavItem } from "@/components/shell/Sidebar";
import { api, requireUser, type AppRow } from "@/lib/api";

export const dynamic = "force-dynamic";

function status(row: AppRow): NavItem["status"] {
  const scan = row.latest_scan;
  if (!scan) return "none";
  return scan.high > 0 ? "high" : scan.medium > 0 ? "medium" : "clean";
}

export default async function SignedInLayout({ children }: { children: React.ReactNode }) {
  const user = await requireUser(); // the real check: the proxy only looked for a cookie
  let apps: AppRow[] = [];
  let apiOk = true;
  try {
    apps = await api.apps();
  } catch (error) {
    // A redirect (session ended between the two calls) must not be swallowed.
    const { unstable_rethrow } = await import("next/navigation");
    unstable_rethrow(error);
    apiOk = false;
  }
  const items: NavItem[] = apps.map((a) => ({ app: a.app, kind: a.kind ?? "app", status: status(a), total: a.latest_scan ? a.latest_scan.total : null }));
  return <Shell items={items} apiOk={apiOk} user={user}>{children}</Shell>;
}

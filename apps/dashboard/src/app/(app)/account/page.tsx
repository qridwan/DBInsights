import type { Metadata } from "next";
import { unstable_rethrow } from "next/navigation";
import { PasswordForm, ProfileForm, RevokeOthers } from "@/components/auth/account";
import { Avatar } from "@/components/shell/UserMenu";
import { Card, PageHeader } from "@/components/ui/Card";
import { Icon } from "@/components/ui/icons";
import { requireUser } from "@/lib/api";
import { authCall } from "@/lib/auth-api";
import { timeAgo } from "@/lib/ui";

export const metadata: Metadata = { title: "Account" };
export const dynamic = "force-dynamic";

interface SessionRow { created_at: string; last_seen_at: string; user_agent: string; ip: string; current: boolean }

function describe(ua: string): string {
  const browser = /Edg\//.test(ua) ? "Edge" : /Chrome\//.test(ua) ? "Chrome" : /Firefox\//.test(ua) ? "Firefox" : /Safari\//.test(ua) ? "Safari" : "Browser";
  const os = /iPhone|iPad/.test(ua) ? "iOS" : /Android/.test(ua) ? "Android" : /Mac OS X/.test(ua) ? "macOS" : /Windows/.test(ua) ? "Windows" : /Linux/.test(ua) ? "Linux" : "unknown system";
  return `${browser} on ${os}`;
}

export default async function Account() {
  const user = await requireUser();
  let sessions: SessionRow[] = [];
  try {
    const result = await authCall<SessionRow[]>("/sessions", undefined, "GET");
    if (result.ok) sessions = result.data;
  } catch (error) {
    unstable_rethrow(error);
  }
  const others = sessions.filter((s) => !s.current).length;
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <PageHeader title="Account and security" description="Your profile, password and the devices signed in to your account." />

      <Card>
        <div className="flex items-center gap-4">
          <Avatar user={user} size={56} />
          <div className="min-w-0">
            <div className="truncate text-lg font-semibold text-ink">{user.name || user.email.split("@")[0]}</div>
            <div className="truncate text-sm text-muted">{user.email}</div>
            <div className="mt-1.5 flex items-center gap-2 text-xs text-muted">
              {user.role === "admin" && <span className="rounded-full bg-brand-soft px-2 py-0.5 font-medium text-brand">Administrator</span>}
              <span>Member since {new Date(user.created_at).toLocaleDateString([], { year: "numeric", month: "long", day: "numeric" })}</span>
            </div>
          </div>
        </div>
      </Card>

      <Card title="Profile"><ProfileForm name={user.name} email={user.email} /></Card>
      <Card title="Password" note="Changing it signs you out everywhere except this device."><PasswordForm email={user.email} /></Card>

      <Card title="Where you are signed in" note="Sessions last 30 days unless you sign out." padded={false}>
        <ul className="divide-y divide-line">
          {sessions.map((s, i) => (
            <li key={i} className="flex items-center gap-3.5 px-5 py-3.5">
              <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-sunken text-muted"><Icon name="devices" /></span>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 text-sm font-medium text-ink">
                  {describe(s.user_agent)}
                  {s.current && <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-medium text-emerald-700 ring-1 ring-inset ring-emerald-200 dark:bg-emerald-500/10 dark:text-emerald-300 dark:ring-emerald-500/25">This device</span>}
                </div>
                <div className="text-xs text-muted">{s.ip ? `${s.ip} · ` : ""}Active {timeAgo(s.last_seen_at)} · signed in {new Date(s.created_at).toLocaleDateString()}</div>
              </div>
            </li>
          ))}
        </ul>
        <div className="border-t border-line p-5"><RevokeOthers others={others} /></div>
      </Card>
    </div>
  );
}

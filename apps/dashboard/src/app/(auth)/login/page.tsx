import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { AuthHeading } from "@/components/auth/AuthHeading";
import { LoginForm } from "@/components/auth/forms";
import { currentUser } from "@/lib/api";
import { safeNext } from "@/lib/auth-api";

export const metadata: Metadata = { title: "Sign in" };
export const dynamic = "force-dynamic";

export default async function Login({ searchParams }: { searchParams: Promise<{ next?: string; reset?: string; expired?: string }> }) {
  const sp = await searchParams;
  const user = await currentUser().catch(() => null);
  if (user) redirect(safeNext(sp.next));
  const notice = sp.reset
    ? { kind: "info" as const, text: "Your password was updated. Sign in with the new one." }
    : sp.expired
      ? { kind: "info" as const, text: "Your session ended. Sign in again to continue." }
      : undefined;
  return (
    <>
      <AuthHeading title="Welcome back" subtitle="Sign in to see your scans and projects." />
      <LoginForm next={sp.next ? safeNext(sp.next) : undefined} notice={notice} />
    </>
  );
}

import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { AuthHeading } from "@/components/auth/AuthHeading";
import { VerifyForm } from "@/components/auth/forms";
import { safeNext } from "@/lib/auth-api";

export const metadata: Metadata = { title: "Verify your email" };
export const dynamic = "force-dynamic";

export default async function Verify({ searchParams }: { searchParams: Promise<{ email?: string; fresh?: string; next?: string }> }) {
  const sp = await searchParams;
  if (!sp.email) redirect("/register");
  return (
    <>
      <AuthHeading icon="mail" title="Check your email" subtitle={<>Enter the 6-digit code we sent to <b className="break-all text-ink">{sp.email}</b>. It expires in 10 minutes.</>} />
      <VerifyForm email={sp.email} next={sp.next ? safeNext(sp.next) : undefined} fresh={Boolean(sp.fresh)} />
      <p className="mt-8 text-center text-sm text-muted">Wrong address? <Link href="/register" className="font-medium text-brand hover:underline">Start again</Link></p>
    </>
  );
}

import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { AuthHeading } from "@/components/auth/AuthHeading";
import { ResetForm } from "@/components/auth/forms";

export const metadata: Metadata = { title: "Choose a new password" };
export const dynamic = "force-dynamic";

export default async function Reset({ searchParams }: { searchParams: Promise<{ email?: string }> }) {
  const { email } = await searchParams;
  if (!email) redirect("/forgot-password");
  return (
    <>
      <AuthHeading icon="shield" title="Choose a new password" subtitle={<>If <b className="break-all text-ink">{email}</b> has an account, we sent it a 6-digit code. Enter it below with your new password.</>} />
      <ResetForm email={email} />
      <p className="mt-8 text-center text-sm text-muted"><Link href="/forgot-password" className="font-medium text-brand hover:underline">Use a different email</Link></p>
    </>
  );
}

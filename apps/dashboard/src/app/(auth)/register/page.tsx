import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { AuthHeading } from "@/components/auth/AuthHeading";
import { RegisterForm } from "@/components/auth/forms";
import { currentUser } from "@/lib/api";

export const metadata: Metadata = { title: "Create your account" };
export const dynamic = "force-dynamic";

export default async function Register() {
  if (await currentUser().catch(() => null)) redirect("/");
  return (
    <>
      <AuthHeading title="Create your account" subtitle="Scan your own projects privately. The built-in test applications are open to everyone." />
      <RegisterForm />
    </>
  );
}

import type { Metadata } from "next";
import { AuthHeading } from "@/components/auth/AuthHeading";
import { ForgotForm } from "@/components/auth/forms";

export const metadata: Metadata = { title: "Reset your password" };

export default function Forgot() {
  return (
    <>
      <AuthHeading icon="lock" title="Forgot your password?" subtitle="Enter your email and we will send a code to choose a new one." />
      <ForgotForm />
    </>
  );
}

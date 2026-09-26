"use client";

import Link from "next/link";
import { useActionState, useEffect, useState } from "react";
import { forgotAction, loginAction, registerAction, resendAction, resetAction, verifyAction, type FormState } from "@/app/(auth)/actions";
import { Countdown, Field, FormMessage, OtpInput, PasswordField, SubmitButton } from "./parts";

const initial: FormState = {};
const link = "font-medium text-brand hover:underline";

export function LoginForm({ next, notice }: { next?: string; notice?: { kind: "info" | "error"; text: string } }) {
  const [state, action] = useActionState(loginAction, initial);
  return (
    <form action={action} className="space-y-5" noValidate={false}>
      {notice && !state.error && <FormMessage {...(notice.kind === "error" ? { error: notice.text } : { info: notice.text })} />}
      <FormMessage error={state.error} />
      {next && <input type="hidden" name="next" value={next} />}
      <Field label="Email" name="email" type="email" autoComplete="email" autoFocus defaultValue={state.values?.email} error={state.fieldErrors?.email} placeholder="you@company.com" />
      <PasswordField autoComplete="current-password" trailing={<Link href="/forgot-password" className="text-xs text-brand hover:underline">Forgot password?</Link>} />
      <SubmitButton pendingLabel="Signing in...">Sign in</SubmitButton>
      <p className="text-center text-sm text-muted">New to DBInsight? <Link href="/register" className={link}>Create an account</Link></p>
    </form>
  );
}

export function RegisterForm() {
  const [state, action] = useActionState(registerAction, initial);
  const [email, setEmail] = useState("");
  return (
    <form action={action} className="space-y-5">
      <FormMessage error={state.error} />
      <Field label="Name" name="name" autoComplete="name" required={false} defaultValue={state.values?.name} placeholder="Ada Lovelace" hint="Optional. Shown in your account menu." />
      <div onChange={(e) => { const t = e.target as HTMLInputElement; if (t.name === "email") setEmail(t.value); }}>
        <Field label="Work email" name="email" type="email" autoComplete="email" defaultValue={state.values?.email} error={state.fieldErrors?.email} placeholder="you@company.com" />
      </div>
      <PasswordField name="password" label="Password" autoComplete="new-password" email={email} showStrength error={state.fieldErrors?.password} />
      <SubmitButton pendingLabel="Creating your account...">Create account</SubmitButton>
      <p className="text-center text-xs text-muted">We will email you a 6-digit code to confirm the address.</p>
      <p className="text-center text-sm text-muted">Already have an account? <Link href="/login" className={link}>Sign in</Link></p>
    </form>
  );
}

function Resend({ email, purpose, initialWait }: { email: string; purpose: "register" | "reset"; initialWait: number }) {
  const [state, action] = useActionState(resendAction, initial);
  const wait = state.wait ?? initialWait;
  return (
    <form action={action} className="text-center">
      <input type="hidden" name="email" value={email} />
      <input type="hidden" name="purpose" value={purpose} />
      <Countdown key={`${wait}-${state.info ?? state.error ?? ""}`} seconds={wait}>
        {(left) => (
          <div className="space-y-2">
            {state.info && <p role="status" className="text-xs text-emerald-600 dark:text-emerald-400">{state.info}</p>}
            {state.error && <p role="alert" className="text-xs text-red-600 dark:text-red-400">{state.error}</p>}
            <p className="text-sm text-muted">
              Did not get it?{" "}
              {left > 0 ? <span className="tabular-nums">Resend in {left}s</span> : <button className={link}>Send a new code</button>}
            </p>
          </div>
        )}
      </Countdown>
    </form>
  );
}

export function VerifyForm({ email, next, fresh }: { email: string; next?: string; fresh: boolean }) {
  const [state, action] = useActionState(verifyAction, initial);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => { if (state.fieldErrors?.code || state.error) setAttempt((n) => n + 1); }, [state]);
  return (
    <div className="space-y-6">
      <form action={action} className="space-y-5">
        <FormMessage error={state.error} />
        {fresh && !state.fieldErrors?.code && !state.error && <FormMessage info={`We sent a 6-digit code to ${email}.`} />}
        <input type="hidden" name="email" value={email} />
        {next && <input type="hidden" name="next" value={next} />}
        <OtpInput error={state.fieldErrors?.code} resetKey={String(attempt)} />
        <SubmitButton pendingLabel="Verifying...">Verify and continue</SubmitButton>
      </form>
      <Resend email={email} purpose="register" initialWait={fresh ? 60 : 0} />
    </div>
  );
}

export function ForgotForm() {
  const [state, action] = useActionState(forgotAction, initial);
  return (
    <form action={action} className="space-y-5">
      <FormMessage error={state.error} />
      <Field label="Email" name="email" type="email" autoComplete="email" autoFocus defaultValue={state.values?.email} error={state.fieldErrors?.email} placeholder="you@company.com" />
      <SubmitButton pendingLabel="Sending code...">Send reset code</SubmitButton>
      <p className="text-center text-sm text-muted"><Link href="/login" className={link}>Back to sign in</Link></p>
    </form>
  );
}

export function ResetForm({ email }: { email: string }) {
  const [state, action] = useActionState(resetAction, initial);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => { if (state.fieldErrors?.code) setAttempt((n) => n + 1); }, [state]);
  return (
    <div className="space-y-6">
      <form action={action} className="space-y-6">
        <FormMessage error={state.error} />
        <input type="hidden" name="email" value={email} />
        <div>
          <p className="mb-2 text-sm font-medium text-ink">Code from your email</p>
          <ResetCode error={state.fieldErrors?.code} resetKey={String(attempt)} />
        </div>
        <PasswordField name="password" label="New password" autoComplete="new-password" email={email} showStrength error={state.fieldErrors?.password} />
        <SubmitButton pendingLabel="Updating password...">Set new password</SubmitButton>
      </form>
      <Resend email={email} purpose="reset" initialWait={60} />
    </div>
  );
}

// The reset code is typed before the new password, so it must not submit the form on its own.
function ResetCode({ error, resetKey }: { error?: string; resetKey: string }) {
  return <OtpInput error={error} resetKey={resetKey} autoSubmit={false} />;
}

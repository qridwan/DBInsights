"use server";

import { redirect } from "next/navigation";
import { authCall, safeNext } from "@/lib/auth-api";
import { clearSession, setSession } from "@/lib/session";

export interface FormState {
  error?: string;
  fieldErrors?: Partial<Record<"email" | "password" | "code" | "name" | "current" | "new", string>>;
  info?: string;
  /** Seconds until a new code may be requested. */
  wait?: number;
  /** What the person typed, so a failed submit does not empty the form. */
  values?: Record<string, string>;
}

const str = (form: FormData, key: string) => String(form.get(key) ?? "");
const enc = encodeURIComponent;
type Signed = { token: string; expires_at: string; claimed_projects?: number };

function failure(result: { code: string; message: string; extra: Record<string, unknown> }, values: Record<string, string>): FormState {
  const wait = typeof result.extra.retry_after === "number" ? result.extra.retry_after : undefined;
  const field = { invalid_email: "email", weak_password: "password", invalid_code: "code", code_expired: "code", too_many_attempts: "code" }[result.code] as keyof NonNullable<FormState["fieldErrors"]> | undefined;
  return field ? { fieldErrors: { [field]: result.message }, wait, values } : { error: result.message, wait, values };
}

export async function loginAction(_: FormState, form: FormData): Promise<FormState> {
  const email = str(form, "email");
  const next = str(form, "next");
  const result = await authCall<Signed>("/login", { email, password: str(form, "password") });
  if (result.ok) {
    await setSession(result.data.token, result.data.expires_at);
    redirect(safeNext(next));
  }
  if (result.code === "email_not_verified") redirect(`/verify?email=${enc(email)}&fresh=1${next ? `&next=${enc(next)}` : ""}`);
  return failure(result, { email });
}

export async function registerAction(_: FormState, form: FormData): Promise<FormState> {
  const values = { email: str(form, "email"), name: str(form, "name") };
  const result = await authCall("/register", { ...values, password: str(form, "password") });
  if (result.ok) redirect(`/verify?email=${enc(values.email.trim().toLowerCase())}&fresh=1`);
  // Asking again too soon still means a code is on its way: go and enter it.
  if (result.code === "cooldown") redirect(`/verify?email=${enc(values.email.trim().toLowerCase())}`);
  return failure(result, values);
}

export async function verifyAction(_: FormState, form: FormData): Promise<FormState> {
  const email = str(form, "email");
  const result = await authCall<Signed>("/verify", { email, code: str(form, "code") });
  if (result.ok) {
    await setSession(result.data.token, result.data.expires_at);
    const claimed = result.data.claimed_projects ?? 0;
    redirect(`${safeNext(str(form, "next"))}${claimed ? `${str(form, "next").includes("?") ? "&" : "?"}claimed=${claimed}` : ""}`);
  }
  return failure(result, { email });
}

export async function resendAction(_: FormState, form: FormData): Promise<FormState> {
  const result = await authCall<{ resend_after: number }>("/resend", { email: str(form, "email"), purpose: str(form, "purpose") });
  if (result.ok) return { info: "A new code is on its way. It can take a minute to arrive.", wait: result.data.resend_after };
  return { error: result.message, wait: typeof result.extra.retry_after === "number" ? result.extra.retry_after : undefined };
}

export async function forgotAction(_: FormState, form: FormData): Promise<FormState> {
  const email = str(form, "email");
  const result = await authCall("/forgot", { email });
  // The answer is the same whether or not the address has an account, and so is what happens next.
  if (result.ok || result.code === "cooldown") redirect(`/reset-password?email=${enc(email.trim().toLowerCase())}`);
  return failure(result, { email });
}

export async function resetAction(_: FormState, form: FormData): Promise<FormState> {
  const email = str(form, "email");
  const result = await authCall("/reset", { email, code: str(form, "code"), password: str(form, "password") });
  if (result.ok) redirect("/login?reset=1");
  return failure(result, { email });
}

export async function logoutAction(): Promise<void> {
  await authCall("/logout");
  await clearSession();
  redirect("/login");
}

// ---- the account page ----------------------------------------------------------------------

export async function updateProfileAction(_: FormState, form: FormData): Promise<FormState> {
  const result = await authCall("/me", { name: str(form, "name") }, "PATCH");
  return result.ok ? { info: "Saved." } : { error: result.message };
}

export async function changePasswordAction(_: FormState, form: FormData): Promise<FormState> {
  const result = await authCall("/password", { current: str(form, "current"), new: str(form, "new") });
  if (result.ok) return { info: "Password changed. Your other devices were signed out." };
  const field = result.code === "invalid_credentials" ? "current" : result.code === "weak_password" ? "new" : undefined;
  return field ? { fieldErrors: { [field]: result.message } } : { error: result.message };
}

export async function revokeOthersAction(_: FormState): Promise<FormState> {
  const result = await authCall<{ revoked: number }>("/sessions/revoke-others", {});
  if (!result.ok) return { error: result.message };
  const n = result.data.revoked;
  return { info: n === 0 ? "There were no other devices signed in." : `Signed out of ${n} other ${n === 1 ? "device" : "devices"}.` };
}

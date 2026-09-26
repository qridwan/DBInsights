"use client";

import { useActionState } from "react";
import { changePasswordAction, revokeOthersAction, updateProfileAction, type FormState } from "@/app/(auth)/actions";
import { Field, FormMessage, PasswordField, SubmitButton } from "./parts";

const initial: FormState = {};

export function ProfileForm({ name, email }: { name: string; email: string }) {
  const [state, action] = useActionState(updateProfileAction, initial);
  return (
    <form action={action} className="space-y-4">
      <FormMessage error={state.error} info={state.info} />
      <Field label="Name" name="name" defaultValue={name} required={false} autoComplete="name" placeholder="Your name" />
      <div>
        <div className="text-sm font-medium text-ink">Email</div>
        <div className="mt-1.5 rounded-lg border border-line bg-sunken px-3.5 py-2.5 text-sm text-muted">{email}</div>
        <p className="mt-1.5 text-xs text-muted">Your email is your sign-in and cannot be changed here.</p>
      </div>
      <div className="max-w-40"><SubmitButton pendingLabel="Saving...">Save changes</SubmitButton></div>
    </form>
  );
}

export function PasswordForm({ email }: { email: string }) {
  const [state, action] = useActionState(changePasswordAction, initial);
  // Reset the fields after a successful change by remounting on the success message.
  return (
    <form key={state.info ?? "form"} action={action} className="space-y-5">
      <FormMessage error={state.error} info={state.info} />
      <PasswordField name="current" label="Current password" autoComplete="current-password" error={state.fieldErrors?.current} />
      <PasswordField name="new" label="New password" autoComplete="new-password" email={email} showStrength error={state.fieldErrors?.new} />
      <div className="max-w-52"><SubmitButton pendingLabel="Updating...">Change password</SubmitButton></div>
    </form>
  );
}

export function RevokeOthers({ others }: { others: number }) {
  const [state, action] = useActionState(revokeOthersAction, initial);
  return (
    <form action={action} className="space-y-3">
      <FormMessage error={state.error} info={state.info} />
      <div className="max-w-60"><SubmitButton variant="quiet" pendingLabel="Signing out...">{others > 0 ? `Sign out ${others} other ${others === 1 ? "device" : "devices"}` : "Sign out other devices"}</SubmitButton></div>
    </form>
  );
}

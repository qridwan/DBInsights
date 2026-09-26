"use client";

import { useEffect, useRef, useState } from "react";
import { useFormStatus } from "react-dom";
import { Icon } from "@/components/ui/icons";

export const input = "block w-full rounded-lg border bg-surface px-3.5 py-2.5 text-sm text-ink placeholder:text-faint transition focus:outline-none focus:ring-2";
const ok = "border-line-strong focus:border-brand focus:ring-brand/25";
const bad = "border-red-400 focus:border-red-500 focus:ring-red-500/20 dark:border-red-500/60";

export function Field({ label, name, type = "text", error, hint, defaultValue, autoComplete, autoFocus, required = true, placeholder, trailing }: {
  label: string; name: string; type?: string; error?: string; hint?: string; defaultValue?: string; autoComplete?: string; autoFocus?: boolean; required?: boolean; placeholder?: string; trailing?: React.ReactNode;
}) {
  const id = `f-${name}`;
  return (
    <div>
      <div className="flex items-baseline justify-between">
        <label htmlFor={id} className="text-sm font-medium text-ink">{label}</label>
        {trailing}
      </div>
      <input id={id} name={name} type={type} defaultValue={defaultValue} autoComplete={autoComplete} autoFocus={autoFocus} required={required} placeholder={placeholder}
        aria-invalid={error ? true : undefined} aria-describedby={error ? `${id}-error` : hint ? `${id}-hint` : undefined}
        className={`${input} mt-1.5 ${error ? bad : ok}`} />
      {error ? <p id={`${id}-error`} role="alert" className="mt-1.5 text-xs text-red-600 dark:text-red-400">{error}</p> : hint ? <p id={`${id}-hint`} className="mt-1.5 text-xs text-muted">{hint}</p> : null}
    </div>
  );
}

export function SubmitButton({ children, pendingLabel, variant = "primary" }: { children: React.ReactNode; pendingLabel?: string; variant?: "primary" | "quiet" }) {
  const { pending } = useFormStatus();
  return (
    <button type="submit" disabled={pending} className={`flex w-full items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-sm font-medium transition disabled:opacity-70 ${variant === "primary" ? "bg-brand text-brand-ink shadow-card hover:opacity-90" : "border border-line-strong bg-surface text-ink hover:bg-sunken"}`}>
      {pending && <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />}
      {pending ? (pendingLabel ?? "Please wait...") : children}
    </button>
  );
}

export function FormMessage({ error, info }: { error?: string; info?: string }) {
  if (error) return <p role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3.5 py-2.5 text-sm text-red-800 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-200">{error}</p>;
  if (info) return <p role="status" className="rounded-lg border border-emerald-200 bg-emerald-50 px-3.5 py-2.5 text-sm text-emerald-800 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-200">{info}</p>;
  return null;
}

// ---- password ------------------------------------------------------------------------------

function assess(password: string, email: string) {
  const local = email.split("@")[0]?.toLowerCase() ?? "";
  const checks = [
    { label: "At least 10 characters", ok: password.length >= 10 },
    { label: "Does not contain your email name", ok: password.length > 0 && !(local.length >= 4 && password.toLowerCase().includes(local)) },
    { label: "Not a repeated or common pattern", ok: password.length > 0 && new Set(password).size >= 4 },
  ];
  const variety = [/[a-z]/, /[A-Z]/, /\d/, /[^A-Za-z0-9]/].filter((r) => r.test(password)).length;
  const raw = (password.length >= 10 ? 1 : 0) + (password.length >= 14 ? 1 : 0) + (password.length >= 18 ? 1 : 0) + (variety >= 3 ? 1 : 0);
  const score = checks.every((c) => c.ok) ? Math.max(1, Math.min(4, raw)) : Math.min(raw, 1);
  return { checks, score: password ? score : 0 };
}

const LEVEL = ["", "Weak", "Fair", "Good", "Strong"];
const COLOR = ["bg-line", "bg-red-500", "bg-amber-500", "bg-emerald-500", "bg-emerald-600"];

export function PasswordField({ name = "password", label = "Password", error, email = "", showStrength = false, autoComplete = "current-password", autoFocus, trailing, hint }: {
  name?: string; label?: string; error?: string; email?: string; showStrength?: boolean; autoComplete?: string; autoFocus?: boolean; trailing?: React.ReactNode; hint?: string;
}) {
  const [value, setValue] = useState("");
  const [show, setShow] = useState(false);
  const id = `f-${name}`;
  const { checks, score } = assess(value, email);
  return (
    <div>
      <div className="flex items-baseline justify-between">
        <label htmlFor={id} className="text-sm font-medium text-ink">{label}</label>
        {trailing}
      </div>
      <div className="relative mt-1.5">
        <input id={id} name={name} type={show ? "text" : "password"} required autoComplete={autoComplete} autoFocus={autoFocus} value={value} onChange={(e) => setValue(e.target.value)}
          aria-invalid={error ? true : undefined} aria-describedby={error ? `${id}-error` : undefined}
          className={`${input} pr-11 ${error ? bad : ok}`} />
        <button type="button" onClick={() => setShow(!show)} className="absolute inset-y-0 right-0 flex w-10 items-center justify-center text-muted hover:text-ink" aria-label={show ? "Hide password" : "Show password"} aria-pressed={show}>
          <Icon name={show ? "eyeOff" : "eye"} className="h-4 w-4" />
          <span className="sr-only">{show ? "Hide" : "Show"}</span>
        </button>
      </div>
      {error && <p id={`${id}-error`} role="alert" className="mt-1.5 text-xs text-red-600 dark:text-red-400">{error}</p>}
      {!error && hint && <p className="mt-1.5 text-xs text-muted">{hint}</p>}
      {showStrength && (
        <div className="mt-3" aria-live="polite">
          <div className="flex items-center gap-2">
            <div className="flex flex-1 gap-1">{[1, 2, 3, 4].map((n) => <span key={n} className={`h-1.5 flex-1 rounded-full transition-colors ${n <= score ? COLOR[score] : "bg-line"}`} />)}</div>
            <span className="w-12 text-right text-xs font-medium text-muted">{LEVEL[score]}</span>
          </div>
          <ul className="mt-2 space-y-1">
            {checks.map((c) => (
              <li key={c.label} className={`flex items-center gap-1.5 text-xs ${c.ok ? "text-emerald-600 dark:text-emerald-400" : "text-muted"}`}>
                <Icon name={c.ok ? "check" : "x"} className="h-3.5 w-3.5" />{c.label}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

// ---- one-time code -------------------------------------------------------------------------

/** Six boxes that behave as one field: type, paste, backspace and arrows all work, and phones can
 *  autofill the code from a message. Fills a hidden `code` input the form submits. */
export function OtpInput({ name = "code", error, resetKey, autoSubmit = true }: { name?: string; error?: string; resetKey?: string; autoSubmit?: boolean }) {
  const [digits, setDigits] = useState<string[]>(Array(6).fill(""));
  const refs = useRef<(HTMLInputElement | null)[]>([]);
  const hidden = useRef<HTMLInputElement>(null);
  const complete = digits.every(Boolean);

  useEffect(() => {
    setDigits(Array(6).fill(""));
    refs.current[0]?.focus();
  }, [resetKey]);

  // Submit as soon as the sixth digit lands (not on the reset form, which still needs a password).
  useEffect(() => {
    if (complete && autoSubmit) hidden.current?.form?.requestSubmit();
  }, [complete, autoSubmit]);

  function put(index: number, raw: string) {
    const only = raw.replace(/\D/g, "");
    if (!only) return;
    const next = [...digits];
    only.split("").slice(0, 6 - index).forEach((d, i) => (next[index + i] = d));
    setDigits(next);
    refs.current[Math.min(index + only.length, 5)]?.focus();
  }

  return (
    <div>
      <input ref={hidden} type="hidden" name={name} value={digits.join("")} readOnly />
      <div className="flex justify-between gap-2" role="group" aria-label="6-digit verification code">
        {digits.map((d, i) => (
          <input key={i} ref={(el) => { refs.current[i] = el; }} value={d} inputMode="numeric" pattern="[0-9]*" maxLength={6} autoComplete={i === 0 ? "one-time-code" : "off"}
            aria-label={`Digit ${i + 1}`} aria-invalid={error ? true : undefined}
            onChange={(e) => (e.target.value ? put(i, e.target.value) : setDigits(digits.map((x, n) => (n === i ? "" : x))))}
            onKeyDown={(e) => {
              if (e.key === "Backspace" && !digits[i] && i > 0) refs.current[i - 1]?.focus();
              if (e.key === "ArrowLeft" && i > 0) refs.current[i - 1]?.focus();
              if (e.key === "ArrowRight" && i < 5) refs.current[i + 1]?.focus();
            }}
            onPaste={(e) => { e.preventDefault(); put(i, e.clipboardData.getData("text")); }}
            onFocus={(e) => e.target.select()}
            className={`h-13 w-full min-w-0 rounded-lg border bg-surface text-center font-mono text-xl font-semibold text-ink transition focus:outline-none focus:ring-2 ${error ? bad : ok}`} style={{ height: 52 }} />
        ))}
      </div>
      {error && <p role="alert" className="mt-2 text-xs text-red-600 dark:text-red-400">{error}</p>}
    </div>
  );
}

/** "Resend code" that waits out the cooldown the server enforces, and shows the countdown. */
export function Countdown({ seconds, children }: { seconds: number; children: (left: number) => React.ReactNode }) {
  const [left, setLeft] = useState(seconds);
  useEffect(() => setLeft(seconds), [seconds]);
  useEffect(() => {
    if (left <= 0) return;
    const t = setTimeout(() => setLeft((n) => n - 1), 1000);
    return () => clearTimeout(t);
  }, [left]);
  return <>{children(left)}</>;
}

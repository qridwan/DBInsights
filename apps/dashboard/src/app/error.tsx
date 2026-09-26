"use client";

import { Icon } from "@/components/ui/icons";

export default function GlobalError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <div className="mx-auto mt-16 max-w-lg rounded-xl border border-line bg-surface p-8 text-center shadow-card">
      <span className="mx-auto flex h-11 w-11 items-center justify-center rounded-full bg-red-50 text-red-600 dark:bg-red-500/10 dark:text-red-400"><Icon name="alert" className="h-5 w-5" /></span>
      <h1 className="mt-4 text-lg font-semibold text-ink">Something went wrong</h1>
      <p className="mt-1 break-words text-sm text-muted">{error.message || "An unexpected error occurred while loading this page."}</p>
      <button onClick={reset} className="mt-5 rounded-lg bg-brand px-4 py-2 text-sm font-medium text-brand-ink hover:opacity-90">Try again</button>
    </div>
  );
}

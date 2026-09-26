import Link from "next/link";
import type { ReactNode } from "react";
import { ApiError } from "@/lib/api";
import { Icon, type IconName } from "./icons";

export function EmptyState({ icon = "info", title, children, action }: { icon?: IconName; title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center rounded-xl border border-dashed border-line-strong bg-surface px-6 py-14 text-center">
      <span className="flex h-11 w-11 items-center justify-center rounded-full bg-sunken text-muted"><Icon name={icon} className="h-5 w-5" /></span>
      <h3 className="mt-4 text-sm font-semibold text-ink">{title}</h3>
      {children && <p className="mt-1 max-w-md text-sm text-muted">{children}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function NoScan({ app }: { app: string }) {
  return (
    <EmptyState icon="activity" title={`No scan of ${app} yet`}>
      Use <b>Run scan</b> at the top right. It takes about ten seconds and runs every evidence layer.
    </EmptyState>
  );
}

export function NeedsDatabase({ view, needs }: { view: string; needs: string }) {
  return (
    <EmptyState icon="database" title={`${view} is not available for a scanned project`}>
      It needs {needs}. A scanned project gets the analysis that needs no database: static source, SQL text and the declared schema.
    </EmptyState>
  );
}

export function ApiProblem({ error }: { error: unknown }) {
  const message = error instanceof ApiError ? error.message : String(error);
  return (
    <div className="rounded-xl border border-red-200 bg-red-50 p-6 text-sm text-red-900 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-200">
      <div className="flex items-center gap-2 font-semibold"><Icon name="alert" className="h-4 w-4" /> The dashboard API is not reachable</div>
      <p className="mt-2 break-words">{message}</p>
      <Link href="/" className="mt-3 inline-block font-medium underline">Try again</Link>
    </div>
  );
}

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`skeleton ${className}`} />;
}

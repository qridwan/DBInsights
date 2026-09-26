import Link from "next/link";
import { ApiError } from "@/lib/api";

export function NoScan({ app }: { app: string }) {
  return (
    <div className="rounded-lg border border-dashed border-slate-300 bg-white p-8 text-center">
      <p className="text-slate-700">No scan of {app} yet.</p>
      <p className="mt-1 text-sm text-slate-500">Use Run scan above; it takes about 10 seconds.</p>
    </div>
  );
}

export function ApiProblem({ error }: { error: unknown }) {
  const message = error instanceof ApiError ? error.message : String(error);
  return (
    <div className="rounded-lg border border-red-200 bg-red-50 p-6 text-sm text-red-800">
      <p className="font-medium">The dashboard API is not reachable.</p>
      <p className="mt-1 break-words">{message}</p>
      <Link href="/" className="mt-3 inline-block underline">Retry</Link>
    </div>
  );
}

export function Card({ title, children, note }: { title: string; children: React.ReactNode; note?: string }) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-3 flex items-baseline justify-between gap-3">
        <h2 className="text-sm font-semibold text-slate-800">{title}</h2>
        {note && <span className="text-xs text-slate-500">{note}</span>}
      </div>
      {children}
    </section>
  );
}

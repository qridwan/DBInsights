"use client";

import { useState } from "react";
import { Icon } from "@/components/ui/icons";

interface Result { explanation: string; recommendation: string }

/** Downstream text only. It cannot change the severity or confidence shown next to it. */
export function Explanation({ scan, finding }: { scan: string; finding: string }) {
  const [state, setState] = useState<"idle" | "loading" | "done" | "error">("idle");
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState("");

  async function load() {
    setState("loading");
    try {
      const response = await fetch(`/api/explain/${scan}/${finding}`);
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail ?? `HTTP ${response.status}`);
      setResult(body);
      setState("done");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setState("error");
    }
  }

  return (
    <div className="rounded-xl border border-line bg-gradient-to-br from-brand-soft to-surface p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2 text-sm font-semibold text-ink"><Icon name="spark" className="h-4 w-4 text-brand" /> AI explanation</div>
        <span className="text-right text-[11px] text-muted">Written from the evidence only. It cannot change severity or confidence.</span>
      </div>
      {state === "idle" && (
        <button onClick={load} className="mt-3 rounded-lg bg-brand px-3.5 py-2 text-sm font-medium text-brand-ink hover:opacity-90">Explain this finding</button>
      )}
      {state === "loading" && <div className="mt-3 space-y-2"><div className="skeleton h-3.5 w-full" /><div className="skeleton h-3.5 w-11/12" /><div className="skeleton h-3.5 w-3/5" /></div>}
      {state === "error" && (
        <p className="mt-3 rounded-lg bg-surface p-3 text-sm text-muted ring-1 ring-line">Not available right now: {error}</p>
      )}
      {state === "done" && result && (
        <div className="mt-3 space-y-3 text-sm leading-relaxed text-ink">
          <p>{result.explanation}</p>
          <div className="rounded-lg bg-surface p-3 ring-1 ring-line"><span className="font-medium">Recommendation. </span><span className="text-muted">{result.recommendation}</span></div>
        </div>
      )}
    </div>
  );
}

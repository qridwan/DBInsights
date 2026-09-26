"use client";

import { useState } from "react";

interface Result {
  explanation: string;
  recommendation: string;
}

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
    <section className="rounded-lg border border-slate-200 bg-white p-4">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-800">AI explanation</h2>
        <span className="text-xs text-slate-500">Written from the evidence above; cannot change the scores.</span>
      </div>
      {state === "idle" && (
        <button onClick={load} className="rounded-md border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-50">
          Explain this finding
        </button>
      )}
      {state === "loading" && <p className="text-sm text-slate-500">Asking the model...</p>}
      {state === "error" && <p className="text-sm text-slate-600">Not available: {error}</p>}
      {state === "done" && result && (
        <div className="space-y-3 text-sm text-slate-800">
          <p>{result.explanation}</p>
          <p className="rounded bg-slate-50 p-3"><span className="font-medium">Recommendation. </span>{result.recommendation}</p>
        </div>
      )}
    </section>
  );
}

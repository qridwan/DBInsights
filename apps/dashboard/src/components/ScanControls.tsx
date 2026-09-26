"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

export function RunScan({ app, project = false }: { app: string; project?: boolean }) {
  const router = useRouter();
  const [state, setState] = useState<"idle" | "running" | "error">("idle");
  const [message, setMessage] = useState("");

  async function run() {
    setState("running");
    setMessage("");
    try {
      const response = await fetch(project ? `/api/project/${app}` : `/api/scan/${app}`, { method: "POST" });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail ?? "scan failed");
      setState("idle");
      router.push(`/${app}?scan=${body.scan_id}`);
      router.refresh();
    } catch (error) {
      setState("error");
      setMessage(error instanceof Error ? error.message : String(error));
    }
  }

  return (
    <div className="flex items-center gap-3">
      <button
        onClick={run}
        disabled={state === "running"}
        className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-60"
      >
        {state === "running" ? (project ? "Scanning..." : "Scanning (about 10 s)...") : project ? "Scan again" : "Run scan"}
      </button>
      {state === "error" && <span className="max-w-md truncate text-xs text-red-700" title={message}>{message}</span>}
    </div>
  );
}

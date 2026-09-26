"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Icon } from "@/components/ui/icons";

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
      {state === "error" && <span role="alert" className="max-w-xs truncate text-xs text-red-600 dark:text-red-400" title={message}>{message}</span>}
      <button onClick={run} disabled={state === "running"} className="inline-flex items-center gap-2 rounded-lg bg-brand px-3.5 py-2 text-sm font-medium text-brand-ink shadow-card hover:opacity-90 disabled:opacity-70">
        {state === "running" ? <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" /> : <Icon name="refresh" />}
        {state === "running" ? (project ? "Scanning..." : "Scanning, about 10 s") : project ? "Scan again" : "Run scan"}
      </button>
    </div>
  );
}

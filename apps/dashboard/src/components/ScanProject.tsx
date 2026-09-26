"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

const field = "mt-1 block w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm";

/** Scan a project that is not one of the built-in apps: a local folder or an https Git URL. */
export function ScanProject() {
  const router = useRouter();
  const [mode, setMode] = useState<"git" | "local">("git");
  const [origin, setOrigin] = useState("");
  const [schema, setSchema] = useState("");
  const [name, setName] = useState("");
  const [state, setState] = useState<"idle" | "running" | "error">("idle");
  const [message, setMessage] = useState("");

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setState("running");
    setMessage("");
    try {
      const response = await fetch("/api/project", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          ...(mode === "git" ? { git_url: origin.trim() } : { path: origin.trim() }),
          ...(schema.trim() ? { schema_path: schema.trim() } : {}),
          ...(name.trim() ? { name: name.trim() } : {}),
        }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail ?? `HTTP ${response.status}`);
      router.push(`/${body.app}?scan=${body.scan_id}`);
      router.refresh();
    } catch (error) {
      setState("error");
      setMessage(error instanceof Error ? error.message : String(error));
      return;
    }
    setState("idle");
  }

  return (
    <form onSubmit={submit} className="space-y-4 rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
      <div>
        <h2 className="text-lg font-medium">Scan a project</h2>
        <p className="mt-1 text-sm text-slate-600">
          Any Prisma project. It gets the analysis that needs no database: static source, SQL text and the declared schema.
          Runtime, actual-schema and data-quality views need a running application and are not available here. Nothing from the
          project is executed or installed.
        </p>
      </div>
      <div className="flex gap-2 text-sm">
        {(["git", "local"] as const).map((m) => (
          <button
            key={m}
            type="button"
            onClick={() => setMode(m)}
            className={`rounded-md px-3 py-1.5 ${mode === m ? "bg-slate-900 text-white" : "border border-slate-300 hover:bg-slate-50"}`}
          >
            {m === "git" ? "Git URL" : "Local folder"}
          </button>
        ))}
      </div>
      <label className="block text-xs text-slate-500">
        {mode === "git" ? "Repository URL (https)" : "Absolute path on the machine running the API"}
        <input
          required
          value={origin}
          onChange={(e) => setOrigin(e.target.value)}
          placeholder={mode === "git" ? "https://github.com/owner/repository" : "/Users/you/projects/my-app"}
          className={field}
        />
      </label>
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="block text-xs text-slate-500">
          Schema path inside the project (optional; default: the schema.prisma with the most models)
          <input value={schema} onChange={(e) => setSchema(e.target.value)} placeholder="prisma/schema.prisma" className={field} />
        </label>
        <label className="block text-xs text-slate-500">
          Name (optional)
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="derived from the folder or repository" className={field} />
        </label>
      </div>
      <div className="flex items-center gap-3">
        <button
          disabled={state === "running" || !origin.trim()}
          className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-60"
        >
          {state === "running" ? (mode === "git" ? "Cloning and scanning..." : "Scanning...") : "Scan project"}
        </button>
        {state === "running" && <span className="text-xs text-slate-500">A large repository can take a few minutes.</span>}
      </div>
      {state === "error" && <p className="rounded-md bg-red-50 p-3 text-sm text-red-800">{message}</p>}
    </form>
  );
}

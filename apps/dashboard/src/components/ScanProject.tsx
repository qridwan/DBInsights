"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { FolderBrowser, type Picked } from "@/components/FolderBrowser";
import { Icon } from "@/components/ui/icons";

const field = "mt-1.5 block w-full rounded-lg border border-line-strong bg-surface px-3 py-2 text-sm text-ink placeholder:text-faint focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/25";

/** Scan a project that is not one of the built-in apps: a local folder or an https Git URL. */
export function ScanProjectDialog({ open, onClose, canScanLocal = false }: { open: boolean; onClose: () => void; canScanLocal?: boolean }) {
  const router = useRouter();
  const dialog = useRef<HTMLDialogElement>(null);
  const [mode, setMode] = useState<"git" | "local">("git");
  const [origin, setOrigin] = useState("");
  const [schema, setSchema] = useState("");
  const [name, setName] = useState("");
  const [advanced, setAdvanced] = useState(false);
  const [browsing, setBrowsing] = useState(false);
  const [picked, setPicked] = useState<Picked | null>(null);
  const [state, setState] = useState<"idle" | "running" | "error">("idle");
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (!open) setBrowsing(false);
    const d = dialog.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    if (!open && d.open) d.close();
  }, [open]);

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
      setState("idle");
      onClose();
      router.push(`/${body.app}?scan=${body.scan_id}`);
      router.refresh();
    } catch (error) {
      setState("error");
      setMessage(error instanceof Error ? error.message : String(error));
    }
  }

  const busy = state === "running";
  return (
    <dialog
      ref={dialog}
      onClose={onClose}
      onClick={(e) => { if (e.target === dialog.current && !busy) onClose(); }}
      className="m-auto w-[min(560px,92vw)] rounded-2xl border border-line bg-surface p-0 text-ink shadow-2xl backdrop:bg-black/50 backdrop:backdrop-blur-sm"
    >
      {browsing && (
        <FolderBrowser
          start={origin.trim().startsWith("/") ? origin.trim() : undefined}
          onCancel={() => setBrowsing(false)}
          onChoose={(p) => { setOrigin(p.path); setPicked(p); setBrowsing(false); }}
        />
      )}
      <form onSubmit={submit} className="p-6" hidden={browsing}>
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold tracking-tight">Scan a project</h2>
            <p className="mt-1 text-sm text-muted">Any Prisma project{canScanLocal ? ", from a Git URL or a folder on this machine" : ", from a public Git URL"}. It stays private to your account.</p>
          </div>
          <button type="button" onClick={onClose} disabled={busy} className="rounded-md p-1 text-muted hover:bg-sunken disabled:opacity-50" aria-label="Close"><Icon name="x" className="h-5 w-5" /></button>
        </div>

        <div className="mt-5 inline-flex rounded-lg bg-sunken p-1 text-sm" role="tablist">
          {(canScanLocal ? (["git", "local"] as const) : (["git"] as const)).map((m) => (
            <button key={m} type="button" role="tab" aria-selected={mode === m} onClick={() => setMode(m)} className={`rounded-md px-3 py-1.5 ${mode === m ? "bg-surface font-medium text-ink shadow-card" : "text-muted"}`}>
              {m === "git" ? "Git URL" : "Local folder"}
            </button>
          ))}
        </div>

        <label className="mt-4 block text-sm font-medium">
          {mode === "git" ? "Repository URL" : "Project folder"}
          <div className={mode === "local" ? "mt-1.5 flex gap-2" : ""}>
            <input required autoFocus value={origin} onChange={(e) => { setOrigin(e.target.value); setPicked(null); }} className={mode === "local" ? field.replace("mt-1.5 ", "") : field}
              placeholder={mode === "git" ? "https://github.com/owner/repository" : "Choose a folder, or paste its path"} />
            {mode === "local" && (
              <button type="button" onClick={() => setBrowsing(true)} className="inline-flex shrink-0 items-center gap-2 rounded-lg border border-line-strong bg-surface px-3.5 py-2 text-sm font-medium text-ink hover:bg-sunken">
                <Icon name="folder" className="h-4 w-4" /> Browse...
              </button>
            )}
          </div>
          <span className="mt-1 block text-xs font-normal text-muted">
            {mode === "git" ? "Public repositories over plain https only." : picked ? (picked.isProject ? "A Prisma project. Ready to scan." : "No schema.prisma directly in this folder; the schema is searched for inside it.") : "A folder on the machine running the dashboard."}
          </span>
        </label>

        <button type="button" onClick={() => setAdvanced(!advanced)} className="mt-4 flex items-center gap-1 text-sm text-muted hover:text-ink">
          <Icon name={advanced ? "chevronDown" : "chevronRight"} className="h-4 w-4" /> Options
        </button>
        {advanced && (
          <div className="mt-2 grid gap-3 sm:grid-cols-2">
            <label className="block text-xs font-medium text-muted">Schema path<input value={schema} onChange={(e) => setSchema(e.target.value)} placeholder="prisma/schema.prisma" className={field} /></label>
            <label className="block text-xs font-medium text-muted">Name<input value={name} onChange={(e) => setName(e.target.value)} placeholder="from the folder or repository" className={field} /></label>
            <p className="text-xs text-muted sm:col-span-2">By default the schema.prisma with the most models is used.</p>
          </div>
        )}

        <div className="mt-5 rounded-lg bg-sunken p-3 text-xs leading-relaxed text-muted">
          <b className="text-ink">What you get:</b> static source analysis, SQL text and the declared schema. Runtime, actual-schema and data-quality views need a running
          application and are not available. Nothing from the project is executed or installed.
        </div>

        {state === "error" && <p role="alert" className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-200">{message}</p>}

        <div className="mt-6 flex items-center justify-end gap-3">
          {busy && <span className="mr-auto text-xs text-muted">{mode === "git" ? "Cloning and analyzing. " : "Analyzing. "}A large repository can take a few minutes.</span>}
          <button type="button" onClick={onClose} disabled={busy} className="rounded-lg px-3 py-2 text-sm text-muted hover:bg-sunken disabled:opacity-50">Cancel</button>
          <button disabled={busy || !origin.trim()} className="inline-flex items-center gap-2 rounded-lg bg-brand px-4 py-2 text-sm font-medium text-brand-ink hover:opacity-90 disabled:opacity-60">
            {busy && <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" />}
            {busy ? "Scanning..." : "Scan project"}
          </button>
        </div>
      </form>
    </dialog>
  );
}

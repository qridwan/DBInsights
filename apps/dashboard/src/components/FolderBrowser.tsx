"use client";

import { useEffect, useMemo, useState } from "react";
import { Icon } from "@/components/ui/icons";

interface Entry { name: string; path: string; is_project: boolean; is_git: boolean }
interface Listing { path: string; parent: string | null; home: string; is_project: boolean; is_git: boolean; entries: Entry[]; truncated: boolean }

export interface Picked { path: string; isProject: boolean }

/** Walk the folders of the machine the dashboard API runs on, and choose one. A web page cannot get
 *  a folder's absolute path from the operating system's own file dialog, so the listing comes from
 *  the API (administrators only). */
export function FolderBrowser({ start, onChoose, onCancel }: { start?: string; onChoose: (picked: Picked) => void; onCancel: () => void }) {
  const [path, setPath] = useState<string | undefined>(start || undefined);
  const [hidden, setHidden] = useState(false);
  const [filter, setFilter] = useState("");
  const [listing, setListing] = useState<Listing | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    const query = new URLSearchParams({ ...(path ? { path } : {}), ...(hidden ? { hidden: "1" } : {}) });
    fetch(`/api/fs?${query}`, { signal: controller.signal })
      .then(async (response) => {
        const body = await response.json();
        if (!response.ok) throw new Error(body.detail ?? `HTTP ${response.status}`);
        setListing(body);
        setFilter("");
      })
      .catch((e) => { if (e.name !== "AbortError") setError(e instanceof Error ? e.message : String(e)); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [path, hidden]);

  const crumbs = useMemo(() => {
    if (!listing) return [];
    const parts = listing.path.split("/").filter(Boolean);
    return [{ label: "/", path: "/" }, ...parts.map((p, i) => ({ label: p, path: "/" + parts.slice(0, i + 1).join("/") }))];
  }, [listing]);

  const shown = (listing?.entries ?? []).filter((e) => e.name.toLowerCase().includes(filter.trim().toLowerCase()));
  const folderName = listing ? listing.path.split("/").filter(Boolean).pop() ?? "/" : "";

  return (
    <div className="p-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold tracking-tight">Choose a project folder</h2>
          <p className="mt-1 text-sm text-muted">Folders on the machine running the dashboard. Open a folder, then choose it.</p>
        </div>
        <button type="button" onClick={onCancel} className="rounded-md p-1 text-muted hover:bg-sunken" aria-label="Back"><Icon name="x" className="h-5 w-5" /></button>
      </div>

      <div className="mt-4 flex items-center gap-1.5">
        <button type="button" disabled={!listing?.parent || loading} onClick={() => listing?.parent && setPath(listing.parent)} className="rounded-md border border-line-strong p-1.5 text-muted hover:bg-sunken disabled:opacity-40" title="Up one folder" aria-label="Up one folder"><Icon name="arrowUp" className="h-4 w-4" /></button>
        <button type="button" disabled={loading} onClick={() => listing && setPath(listing.home)} className="rounded-md border border-line-strong p-1.5 text-muted hover:bg-sunken disabled:opacity-40" title="Home folder" aria-label="Home folder"><Icon name="home" className="h-4 w-4" /></button>
        <nav aria-label="Current folder" className="flex min-w-0 flex-1 items-center gap-0.5 overflow-x-auto rounded-md bg-sunken px-2 py-1.5 text-xs">
          {crumbs.map((c, i) => (
            <span key={c.path} className="flex shrink-0 items-center">
              {i > 0 && <Icon name="chevronRight" className="h-3 w-3 text-faint" />}
              <button type="button" onClick={() => setPath(c.path)} className={`rounded px-1 py-0.5 hover:bg-line ${i === crumbs.length - 1 ? "font-semibold text-ink" : "text-muted"}`}>{c.label}</button>
            </span>
          ))}
        </nav>
      </div>

      <div className="relative mt-3">
        <Icon name="search" className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-faint" />
        <input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Filter this folder" aria-label="Filter folders" className="w-full rounded-lg border border-line-strong bg-surface py-2 pl-8 pr-3 text-sm text-ink placeholder:text-faint focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/25" />
      </div>

      {listing?.is_project && (
        <div className="mt-3 flex items-center gap-2 rounded-lg bg-brand-soft px-3 py-2 text-sm text-ink"><Icon name="check" className="h-4 w-4 text-brand" /> This folder looks like a Prisma project.</div>
      )}

      <div className="mt-3 h-72 overflow-y-auto rounded-lg border border-line" aria-busy={loading}>
        {error ? (
          <div className="p-4 text-sm"><p role="alert" className="text-red-600 dark:text-red-400">{error}</p><button type="button" onClick={() => setPath(undefined)} className="mt-2 text-brand hover:underline">Go to the home folder</button></div>
        ) : loading && !listing ? (
          <div className="space-y-2 p-3">{[0, 1, 2, 3, 4].map((i) => <div key={i} className="skeleton h-9" />)}</div>
        ) : shown.length === 0 ? (
          <p className="p-6 text-center text-sm text-muted">{filter ? "No folder matches the filter." : "There are no folders inside this one."}</p>
        ) : (
          <ul className={loading ? "opacity-60" : ""}>
            {shown.map((e) => (
              <li key={e.path}>
                <button type="button" onClick={() => setPath(e.path)} className="flex w-full items-center gap-3 border-b border-line px-3 py-2.5 text-left last:border-0 hover:bg-sunken">
                  <Icon name="folder" className={`h-[18px] w-[18px] shrink-0 ${e.is_project ? "text-brand" : "text-faint"}`} />
                  <span className="min-w-0 flex-1 truncate text-sm text-ink">{e.name}</span>
                  {e.is_project && <span className="shrink-0 rounded-full bg-brand-soft px-2 py-0.5 text-[11px] font-medium text-brand">Prisma project</span>}
                  {e.is_git && <span className="shrink-0 rounded-full bg-sunken px-2 py-0.5 text-[11px] text-muted ring-1 ring-inset ring-line">Git</span>}
                  <Icon name="chevronRight" className="h-4 w-4 shrink-0 text-faint" />
                </button>
              </li>
            ))}
            {listing?.truncated && <li className="px-3 py-2 text-xs text-muted">Only the first {listing.entries.length} folders are shown. Use the filter to find yours.</li>}
          </ul>
        )}
      </div>

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
        <label className="flex items-center gap-2 text-xs text-muted"><input type="checkbox" checked={hidden} onChange={(e) => setHidden(e.target.checked)} className="accent-[var(--brand)]" /> Show hidden folders</label>
        <div className="flex items-center gap-3">
          <button type="button" onClick={onCancel} className="rounded-lg px-3 py-2 text-sm text-muted hover:bg-sunken">Cancel</button>
          <button type="button" disabled={!listing || loading || Boolean(error)} onClick={() => listing && onChoose({ path: listing.path, isProject: listing.is_project })} className="max-w-56 truncate rounded-lg bg-brand px-4 py-2 text-sm font-medium text-brand-ink hover:opacity-90 disabled:opacity-60">
            Choose &ldquo;{folderName}&rdquo;
          </button>
        </div>
      </div>
    </div>
  );
}

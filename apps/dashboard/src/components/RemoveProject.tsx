"use client";

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { Icon } from "@/components/ui/icons";

/** Remove one of your scanned projects: its scans, findings and the cloned copy. Asks first. */
export function RemoveProject({ name }: { name: string }) {
  const router = useRouter();
  const dialog = useRef<HTMLDialogElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function remove() {
    setBusy(true);
    setError("");
    try {
      const response = await fetch(`/api/project/${encodeURIComponent(name)}`, { method: "DELETE" });
      if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail ?? `HTTP ${response.status}`);
      dialog.current?.close();
      router.push("/");
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  }

  return (
    <>
      <button onClick={() => dialog.current?.showModal()} className="inline-flex items-center gap-1.5 rounded-lg border border-line-strong bg-surface px-3 py-2 text-sm text-muted hover:border-red-300 hover:text-red-600" title="Remove this project">
        <Icon name="trash" className="h-4 w-4" /> Remove
      </button>
      <dialog ref={dialog} className="m-auto w-[min(440px,92vw)] rounded-2xl border border-line bg-surface p-6 text-ink shadow-2xl backdrop:bg-black/50 backdrop:backdrop-blur-sm">
        <h2 className="text-lg font-semibold">Remove {name}?</h2>
        <p className="mt-2 text-sm text-muted">This deletes all of its scans and findings, and the cloned copy. It cannot be undone. You can scan the project again later.</p>
        {error && <p role="alert" className="mt-3 text-sm text-red-600">{error}</p>}
        <div className="mt-6 flex justify-end gap-3">
          <button onClick={() => dialog.current?.close()} disabled={busy} className="rounded-lg px-3 py-2 text-sm text-muted hover:bg-sunken">Cancel</button>
          <button onClick={remove} disabled={busy} className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-60">{busy ? "Removing..." : "Remove project"}</button>
        </div>
      </dialog>
    </>
  );
}

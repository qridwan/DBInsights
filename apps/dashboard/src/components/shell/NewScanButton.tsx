"use client";

import { Icon } from "@/components/ui/icons";
import { useScanDialog } from "./ScanDialogContext";

export function NewScanButton({ label = "Scan a project", variant = "primary" }: { label?: string; variant?: "primary" | "quiet" }) {
  const { open } = useScanDialog();
  return (
    <button onClick={open} className={`inline-flex items-center gap-2 rounded-lg px-3.5 py-2 text-sm font-medium ${variant === "primary" ? "bg-brand text-brand-ink shadow-card hover:opacity-90" : "border border-line-strong bg-surface text-ink hover:bg-sunken"}`}>
      <Icon name="plus" /> {label}
    </button>
  );
}

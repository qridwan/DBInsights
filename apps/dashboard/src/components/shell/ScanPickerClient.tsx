"use client";

import { useSearchParams } from "next/navigation";
import { ScanPicker } from "./ScanPicker";
import type { ScanRow } from "@/lib/api";

/** Reads `?scan=` in the browser and hands the list to the picker (defaults to the latest scan). */
export function ScanPickerClient({ scans }: { scans: ScanRow[] }) {
  const current = useSearchParams().get("scan") ?? scans[0]?.scan_id ?? "";
  return <ScanPicker scans={scans.map((s) => ({ id: s.scan_id, started_at: s.started_at, total: s.total, high: s.high }))} current={current} />;
}

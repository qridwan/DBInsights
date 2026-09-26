"use client";

import { usePathname, useRouter } from "next/navigation";
import { shortTime } from "@/lib/ui";

export interface ScanOption { id: string; started_at: string; total: number; high: number }

/** Switch which scan every tab shows. The choice lives in the URL (`?scan=`). */
export function ScanPicker({ scans, current }: { scans: ScanOption[]; current: string }) {
  const router = useRouter();
  const path = usePathname();
  if (scans.length < 2) return null;
  return (
    <label className="flex items-center gap-2 text-xs text-muted">
      Scan
      <select
        value={current}
        onChange={(e) => router.push(`${path}?scan=${e.target.value}`)}
        className="rounded-lg border border-line-strong bg-surface py-1.5 pl-2.5 pr-7 text-xs text-ink focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/25"
      >
        {scans.map((s, i) => (
          <option key={s.id} value={s.id}>
            {i === 0 ? "Latest · " : ""}{shortTime(s.started_at)} · {s.total} findings{s.high ? `, ${s.high} high` : ""}
          </option>
        ))}
      </select>
    </label>
  );
}

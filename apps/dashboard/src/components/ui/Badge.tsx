import type { Layer, Level } from "@/lib/api";
import { layerInfo } from "@/lib/ui";

const pill = "inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset";

const SEVERITY: Record<Level, { pill: string; dot: string; label: string }> = {
  HIGH: { pill: "bg-red-50 text-red-700 ring-red-200 dark:bg-red-500/10 dark:text-red-300 dark:ring-red-500/25", dot: "bg-red-500", label: "High" },
  MEDIUM: { pill: "bg-amber-50 text-amber-800 ring-amber-200 dark:bg-amber-500/10 dark:text-amber-300 dark:ring-amber-500/25", dot: "bg-amber-500", label: "Medium" },
  LOW: { pill: "bg-slate-100 text-slate-700 ring-slate-200 dark:bg-slate-500/10 dark:text-slate-300 dark:ring-slate-500/25", dot: "bg-slate-400", label: "Low" },
};

export const SEVERITY_COLOR: Record<Level, string> = { HIGH: "#ef4444", MEDIUM: "#f59e0b", LOW: "#94a3b8" };

export function SeverityBadge({ level }: { level: Level }) {
  const s = SEVERITY[level];
  return (
    <span className={`${pill} ${s.pill}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${s.dot}`} />
      {s.label}
    </span>
  );
}

/** Confidence as a three-step meter: how sure the analyzer is, at a glance. */
export function ConfidenceMeter({ level, showLabel = true }: { level: Level; showLabel?: boolean }) {
  const filled = { LOW: 1, MEDIUM: 2, HIGH: 3 }[level];
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-muted" title={`${level.toLowerCase()} confidence in this finding`}>
      <span className="flex items-end gap-0.5" aria-hidden="true">
        {[1, 2, 3].map((n) => (
          <span key={n} className={`w-1 rounded-sm ${n <= filled ? "bg-ink" : "bg-line-strong"}`} style={{ height: 4 + n * 3 }} />
        ))}
      </span>
      {showLabel && <span>{level.charAt(0) + level.slice(1).toLowerCase()} confidence</span>}
    </span>
  );
}

export function LayerChip({ layer, muted = false, size = "sm" }: { layer: Layer; muted?: boolean; size?: "sm" | "xs" }) {
  const info = layerInfo(layer);
  return (
    <span
      className={`${pill} ${size === "xs" ? "px-1.5 text-[11px]" : ""} ${muted ? "bg-transparent text-faint ring-line" : info.chip}`}
      title={muted ? `${info.label}: no evidence` : info.label}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${muted ? "bg-line-strong" : info.dot}`} />
      {info.label}
    </span>
  );
}

export function NewBadge() {
  return <span className={`${pill} bg-brand-soft text-brand ring-brand/25`}>New</span>;
}

export function RuleTag({ rule }: { rule: string }) {
  return <code className="rounded bg-sunken px-1.5 py-0.5 font-mono text-[11px] text-muted">{rule}</code>;
}

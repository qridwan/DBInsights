import { Icon } from "./icons";
import { Sparkline } from "./Sparkline";

/** A headline number with its change since the previous scan. `goodWhenDown`: fewer is better. */
export function Stat({
  label,
  value,
  previous,
  history,
  tone = "ink",
  hint,
  goodWhenDown = true,
}: {
  label: string;
  value: number | string;
  previous?: number | null;
  history?: number[];
  tone?: "ink" | "red" | "amber" | "green";
  hint?: string;
  goodWhenDown?: boolean;
}) {
  const color = { ink: "text-ink", red: "text-red-600 dark:text-red-400", amber: "text-amber-600 dark:text-amber-400", green: "text-emerald-600 dark:text-emerald-400" }[tone];
  const stroke = { ink: "var(--faint)", red: "#ef4444", amber: "#f59e0b", green: "#10b981" }[tone];
  const delta = typeof value === "number" && typeof previous === "number" ? value - previous : null;
  const good = delta === null || delta === 0 ? null : goodWhenDown ? delta < 0 : delta > 0;
  return (
    <div className="rounded-xl border border-line bg-surface p-4 shadow-card">
      <div className="flex items-start justify-between gap-2">
        <div className="text-xs font-medium uppercase tracking-wide text-muted">{label}</div>
        {history && history.length > 1 && <span className={color}><Sparkline values={history} color={stroke} /></span>}
      </div>
      <div className={`mt-2 text-3xl font-semibold tabular-nums tracking-tight ${color}`}>{value}</div>
      <div className="mt-1 h-4 text-xs text-muted">
        {delta !== null ? (
          delta === 0 ? (
            "No change since the previous scan"
          ) : (
            <span className={`inline-flex items-center gap-1 font-medium ${good ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400"}`}>
              <Icon name={delta > 0 ? "arrowUp" : "arrowDown"} className="h-3 w-3" />
              {Math.abs(delta)} since the previous scan
            </span>
          )
        ) : (
          hint ?? ""
        )}
      </div>
    </div>
  );
}

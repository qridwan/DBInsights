import type { Layer } from "./api";

// Declared and actual schema get related but distinct colours on purpose: they are separate
// evidence sources and the dashboard never blends them.
export const LAYERS: { id: Layer; label: string; chip: string; dot: string }[] = [
  { id: "STATIC_SOURCE", label: "Static source", chip: "bg-sky-50 text-sky-800 ring-sky-200 dark:bg-sky-500/10 dark:text-sky-300 dark:ring-sky-500/25", dot: "bg-sky-500" },
  { id: "DECLARED_SCHEMA", label: "Declared schema", chip: "bg-indigo-50 text-indigo-800 ring-indigo-200 dark:bg-indigo-500/10 dark:text-indigo-300 dark:ring-indigo-500/25", dot: "bg-indigo-500" },
  { id: "ACTUAL_SCHEMA", label: "Actual schema", chip: "bg-fuchsia-50 text-fuchsia-800 ring-fuchsia-200 dark:bg-fuchsia-500/10 dark:text-fuchsia-300 dark:ring-fuchsia-500/25", dot: "bg-fuchsia-500" },
  { id: "SQL", label: "SQL", chip: "bg-amber-50 text-amber-800 ring-amber-200 dark:bg-amber-500/10 dark:text-amber-300 dark:ring-amber-500/25", dot: "bg-amber-500" },
  { id: "RUNTIME", label: "Runtime", chip: "bg-emerald-50 text-emerald-800 ring-emerald-200 dark:bg-emerald-500/10 dark:text-emerald-300 dark:ring-emerald-500/25", dot: "bg-emerald-500" },
  { id: "DATA_QUALITY", label: "Data quality", chip: "bg-cyan-50 text-cyan-800 ring-cyan-200 dark:bg-cyan-500/10 dark:text-cyan-300 dark:ring-cyan-500/25", dot: "bg-cyan-500" },
];

export const layerInfo = (id: Layer) => LAYERS.find((l) => l.id === id)!;

export const RULES = [
  "N_PLUS_ONE_IN_LOOP",
  "RUNTIME_N_PLUS_ONE",
  "MISSING_INDEX_ON_FILTERED_FIELD",
  "MISSING_PAGINATION",
  "UNBOUNDED_MUTATION",
  "SEQUENTIAL_INDEPENDENT_AWAITS",
  "INDEX_NOT_DECLARED",
  "DECLARED_INDEX_NOT_APPLIED",
  "NULL_SPIKE",
  "DUPLICATE_SPIKE",
  "DISTRIBUTION_SHIFT",
  "ORPHANED_FOREIGN_KEY",
];

export const fmtMs = (ms: number) => (ms >= 100 ? `${ms.toFixed(0)} ms` : `${ms.toFixed(1)} ms`);
export const pct = (v: number | null) => (v === null ? "n/a" : `${(v * 100).toFixed(1)}%`);

/** A short human label for a normalized SQL statement: operation, table, and its filter. */
export function shapeLabel(sql: string, max = 34): string {
  const flat = sql.replace(/\s+/g, " ").trim();
  const kind = flat.split(" ")[0]?.toUpperCase() ?? "";
  const table = /(?:FROM|INTO|UPDATE)\s+(?:"?\w+"?\.)?"?(\w+)"?/i.exec(flat)?.[1] ?? "";
  const where = /WHERE\s+(.*?)(?:\s+(?:ORDER|GROUP|LIMIT|OFFSET)\b|$)/i.exec(flat)?.[1]?.replace(/"?\w+"?\."/g, "") ?? "";
  const label = [kind, table, where && `· ${where.replace(/"/g, "")}`].filter(Boolean).join(" ");
  return label.length > max ? `${label.slice(0, max - 1)}…` : label;
}

export function timeAgo(iso: string, now = Date.now()): string {
  const seconds = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000));
  if (seconds < 45) return "just now";
  const units: [number, string][] = [[60, "minute"], [3600, "hour"], [86400, "day"]];
  let out = `${Math.round(seconds / 86400)} days ago`;
  for (const [size, name] of units) {
    if (seconds < size * (name === "day" ? 30 : name === "hour" ? 24 : 60)) {
      const n = Math.max(1, Math.round(seconds / size));
      out = `${n} ${name}${n === 1 ? "" : "s"} ago`;
      break;
    }
  }
  return out;
}

export const shortTime = (iso: string) =>
  new Date(iso).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });

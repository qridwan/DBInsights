import type { Layer, Level } from "./api";

// Declared and actual schema get related but distinct colours on purpose: they are separate
// evidence sources and the dashboard never blends them.
export const LAYERS: { id: Layer; label: string; chip: string; dot: string }[] = [
  { id: "STATIC_SOURCE", label: "Static source", chip: "bg-sky-100 text-sky-800 ring-sky-300", dot: "bg-sky-500" },
  { id: "DECLARED_SCHEMA", label: "Declared schema", chip: "bg-indigo-100 text-indigo-800 ring-indigo-300", dot: "bg-indigo-500" },
  { id: "ACTUAL_SCHEMA", label: "Actual schema", chip: "bg-fuchsia-100 text-fuchsia-800 ring-fuchsia-300", dot: "bg-fuchsia-500" },
  { id: "SQL", label: "SQL", chip: "bg-amber-100 text-amber-800 ring-amber-300", dot: "bg-amber-500" },
  { id: "RUNTIME", label: "Runtime", chip: "bg-emerald-100 text-emerald-800 ring-emerald-300", dot: "bg-emerald-500" },
  { id: "DATA_QUALITY", label: "Data quality", chip: "bg-cyan-100 text-cyan-800 ring-cyan-300", dot: "bg-cyan-500" },
];

export const layerInfo = (id: Layer) => LAYERS.find((l) => l.id === id)!;

export const SEVERITY_STYLE: Record<Level, string> = {
  HIGH: "bg-red-100 text-red-800 ring-red-300",
  MEDIUM: "bg-orange-100 text-orange-800 ring-orange-300",
  LOW: "bg-slate-100 text-slate-700 ring-slate-300",
};

export const CONFIDENCE_STYLE: Record<Level, string> = {
  HIGH: "bg-slate-800 text-white ring-slate-800",
  MEDIUM: "bg-slate-200 text-slate-800 ring-slate-300",
  LOW: "bg-white text-slate-600 ring-slate-300",
};

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

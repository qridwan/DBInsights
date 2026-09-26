import type { Layer, Level } from "@/lib/api";
import { CONFIDENCE_STYLE, layerInfo, SEVERITY_STYLE } from "@/lib/ui";

const base = "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset";

export function SeverityBadge({ level }: { level: Level }) {
  return <span className={`${base} ${SEVERITY_STYLE[level]}`}>{level}</span>;
}

export function ConfidenceBadge({ level }: { level: Level }) {
  return (
    <span className={`${base} ${CONFIDENCE_STYLE[level]}`} title="Analyzer's confidence in this finding">
      {level} confidence
    </span>
  );
}

export function LayerChip({ layer, muted = false }: { layer: Layer; muted?: boolean }) {
  const info = layerInfo(layer);
  return (
    <span
      className={`${base} ${muted ? "bg-white text-slate-400 ring-slate-200" : info.chip}`}
      title={muted ? `${info.label}: no evidence` : info.label}
    >
      <span className={`mr-1.5 inline-block h-1.5 w-1.5 rounded-full ${muted ? "bg-slate-300" : info.dot}`} />
      {info.label}
    </span>
  );
}

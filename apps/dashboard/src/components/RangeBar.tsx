import type { Detection } from "@/lib/api";

const W = 320;
const ROW = 8;

/**
 * The current value drawn against the range each detector learned from the column's own history.
 * The shaded band is the widest of them; the thin bars are the individual detectors.
 */
export function RangeBar({ value, detections, anomalous }: { value: number; detections: Detection[]; anomalous: boolean }) {
  const ranges = detections.filter((d) => d.evaluated && d.lower !== null && d.upper !== null);
  const lows = ranges.map((d) => Math.max(d.lower as number, 0));
  const highs = ranges.map((d) => d.upper as number);
  const max = Math.max(value, ...highs, 0.01) * 1.12;
  const x = (v: number) => Math.min(Math.max((v / max) * W, 0), W);
  const height = 20 + ranges.length * ROW;
  return (
    <svg viewBox={`0 0 ${W} ${height}`} className="w-full" role="img" aria-label={`Value ${value.toFixed(3)} against the learned ranges`}>
      <rect x={0} y={7} width={W} height={4} rx={2} fill="var(--line)" />
      {ranges.length > 0 && (
        <rect x={x(Math.min(...lows))} y={5} width={Math.max(x(Math.max(...highs)) - x(Math.min(...lows)), 3)} height={8} rx={3} fill="#10b981" fillOpacity={0.28} />
      )}
      {ranges.map((d, i) => (
        <rect key={d.detector} x={x(Math.max(d.lower as number, 0))} y={20 + i * ROW} width={Math.max(x(d.upper as number) - x(Math.max(d.lower as number, 0)), 1.5)} height={3} rx={1.5} fill="#10b981" fillOpacity={0.7} />
      ))}
      <circle cx={x(value)} cy={9} r={6} fill={anomalous ? "#ef4444" : "#10b981"} stroke="var(--surface)" strokeWidth={2} />
    </svg>
  );
}

import type { Detection } from "@/lib/api";

const W = 320;
const ROW = 9;

/**
 * The current value drawn against the range each detector learned from the column's own history.
 * The shaded band is the widest of them; the thin bars are the individual detectors.
 */
export function RangeBar({
  value,
  detections,
  anomalous,
}: {
  value: number;
  detections: Detection[];
  anomalous: boolean;
}) {
  const ranges = detections.filter((d) => d.evaluated && d.lower !== null && d.upper !== null);
  const lows = ranges.map((d) => Math.max(d.lower as number, 0));
  const highs = ranges.map((d) => d.upper as number);
  const max = Math.max(value, ...highs, 0.01) * 1.15;
  const x = (v: number) => Math.min(Math.max((v / max) * W, 0), W);
  const height = 16 + ranges.length * ROW;
  return (
    <svg viewBox={`0 0 ${W} ${height}`} className="w-full max-w-sm" role="img"
      aria-label={`Value ${value.toFixed(3)} against learned ranges`}>
      <line x1={0} x2={W} y1={8} y2={8} stroke="#e2e8f0" />
      {ranges.length > 0 && (
        <rect x={x(Math.min(...lows))} y={2} width={Math.max(x(Math.max(...highs)) - x(Math.min(...lows)), 2)}
          height={12} rx={3} fill="#bbf7d0" />
      )}
      {ranges.map((d, i) => (
        <g key={d.detector}>
          <rect x={x(Math.max(d.lower as number, 0))} y={17 + i * ROW}
            width={Math.max(x(d.upper as number) - x(Math.max(d.lower as number, 0)), 1.5)} height={3} fill="#4ade80" />
        </g>
      ))}
      <circle cx={x(value)} cy={8} r={5} fill={anomalous ? "#dc2626" : "#16a34a"} stroke="white" strokeWidth={1.5} />
    </svg>
  );
}

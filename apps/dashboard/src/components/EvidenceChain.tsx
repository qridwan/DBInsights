import type { Evidence, Layer } from "@/lib/api";
import { LAYERS, layerInfo } from "@/lib/ui";
import { LayerChip } from "@/components/ui/Badge";

/**
 * The evidence chain: every item that supports the finding, in order, each labelled with the layer
 * it came from. Layers that contributed nothing are listed too, so what is NOT known is as visible
 * as what is. Layers that were not run for this scan are shown separately as "not run".
 */
export function EvidenceChain({ evidence, layers, ran }: { evidence: Evidence[]; layers: Layer[]; ran?: Layer[] }) {
  const contributed = new Set(layers);
  const notRun = new Set(ran ? LAYERS.map((l) => l.id).filter((id) => !ran.includes(id)) : []);
  const considered = LAYERS.length - notRun.size;
  return (
    <div>
      <div className="mb-4 rounded-lg bg-sunken p-3">
        <div className="flex items-baseline justify-between gap-2">
          <span className="text-sm font-medium text-ink">{contributed.size} of {considered} layers contributed evidence</span>
          {notRun.size > 0 && <span className="text-xs text-muted">{notRun.size} not run in this scan</span>}
        </div>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {LAYERS.filter((l) => !notRun.has(l.id)).map((l) => <LayerChip key={l.id} layer={l.id} muted={!contributed.has(l.id)} size="xs" />)}
          {LAYERS.filter((l) => notRun.has(l.id)).map((l) => (
            <span key={l.id} className="inline-flex items-center rounded-full border border-dashed border-line-strong px-1.5 py-0.5 text-[11px] text-faint" title={`${l.label}: not run for this scan`}>{l.label}: not run</span>
          ))}
        </div>
      </div>

      <ol className="relative space-y-3">
        <span className="absolute bottom-3 left-[11px] top-3 w-px bg-line" aria-hidden="true" />
        {evidence.map((item, index) => {
          const info = layerInfo(item.source);
          return (
            <li key={index} className="relative flex gap-3">
              <span className="relative z-10 mt-3 flex h-[23px] w-[23px] shrink-0 items-center justify-center rounded-full border border-line bg-surface text-[10px] font-semibold text-muted">
                {index + 1}
              </span>
              <div className="min-w-0 flex-1 rounded-lg border border-line bg-surface p-3.5">
                <div className="mb-1.5 flex flex-wrap items-center gap-2">
                  <LayerChip layer={item.source} size="xs" />
                  {item.file && <code className="truncate font-mono text-[11px] text-muted">{item.file}{item.line ? `:${item.line}` : ""}</code>}
                </div>
                <p className="text-sm leading-relaxed text-ink">{item.description}</p>
                {item.data && (
                  <details className="group mt-2">
                    <summary className="cursor-pointer select-none text-xs text-muted hover:text-ink">Structured data</summary>
                    <pre className="mt-2 max-h-56 overflow-auto rounded-md bg-sunken p-2.5 font-mono text-[11px] leading-relaxed text-muted">{JSON.stringify(item.data, null, 2)}</pre>
                  </details>
                )}
              </div>
              <span className="sr-only">from {info.label}</span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

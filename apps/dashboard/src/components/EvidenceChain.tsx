import type { Evidence, Layer } from "@/lib/api";
import { LAYERS, layerInfo } from "@/lib/ui";
import { LayerChip } from "./Badges";

/**
 * The evidence chain: every item that supports the finding, in order, each labelled with the layer
 * it came from. Layers that contributed nothing are listed too, so what is NOT known is as visible
 * as what is.
 */
export function EvidenceChain({ evidence, layers }: { evidence: Evidence[]; layers: Layer[] }) {
  const contributed = new Set(layers);
  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium text-slate-700">
          {contributed.size} of {LAYERS.length} layers contributed
        </span>
        {LAYERS.map((l) => (
          <LayerChip key={l.id} layer={l.id} muted={!contributed.has(l.id)} />
        ))}
      </div>
      <ol className="relative space-y-3 border-l-2 border-slate-200 pl-5">
        {evidence.map((item, index) => {
          const info = layerInfo(item.source);
          return (
            <li key={index} className="relative">
              <span
                className={`absolute -left-[27px] top-1.5 h-3 w-3 rounded-full ring-4 ring-slate-50 ${info.dot}`}
              />
              <div className="rounded-lg border border-slate-200 bg-white p-3 shadow-sm">
                <div className="mb-1 flex flex-wrap items-center gap-2">
                  <LayerChip layer={item.source} />
                  {item.file && (
                    <code className="text-xs text-slate-500">
                      {item.file}
                      {item.line ? `:${item.line}` : ""}
                    </code>
                  )}
                </div>
                <p className="text-sm text-slate-800">{item.description}</p>
                {item.data && (
                  <details className="mt-2">
                    <summary className="cursor-pointer text-xs text-slate-500">structured data</summary>
                    <pre className="mt-1 max-h-56 overflow-auto rounded bg-slate-50 p-2 text-xs text-slate-700">
                      {JSON.stringify(item.data, null, 2)}
                    </pre>
                  </details>
                )}
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

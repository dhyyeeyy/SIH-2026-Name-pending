import type { TraceEntry } from "../types/agent"

const STEP_LABELS: Record<string, string> = {
  router_decision: "Routed",
  rag_retrieval: "Retrieved",
  rag_skipped: "Skipped document search",
  vision_extraction: "Read document",
  vision_extraction_failed: "Retry — malformed output",
  image_downscaled: "Resized image",
  rag_ingest: "Stored in knowledge base",
  model_response: "Generated",
  failed: "Gave up",
}

function formatDetail(detail: TraceEntry["detail"]): string {
  if (typeof detail === "string") return detail
  return `${detail.role} · confidence ${detail.confidence.toFixed(2)}${detail.override ? " · override" : ""}`
}

interface TraceViewProps {
  trace: TraceEntry[]
}

export function TraceView({ trace }: TraceViewProps) {
  if (trace.length === 0) return null

  return (
    <details className="group mt-2 rounded-lg border border-white/10 bg-obsidian/60">
      <summary className="cursor-pointer select-none px-3 py-2 font-mono text-[11px] uppercase tracking-wider text-ash/70 hover:text-ash">
        Trace · {trace.length} step{trace.length !== 1 ? "s" : ""}
      </summary>
      <ol className="space-y-1.5 px-3 pb-3">
        {trace.map((entry, i) => {
          const isFailure = entry.step === "vision_extraction_failed" || entry.step === "failed"
          return (
            <li key={i} className="flex items-baseline gap-2 font-mono text-xs">
              <span className={isFailure ? "text-ember-dim" : "text-ember"}>{String(i + 1).padStart(2, "0")}</span>
              <span className="text-bone/90">{STEP_LABELS[entry.step] ?? entry.step}</span>
              <span className="truncate text-ash/70">{formatDetail(entry.detail)}</span>
            </li>
          )
        })}
      </ol>
    </details>
  )
}

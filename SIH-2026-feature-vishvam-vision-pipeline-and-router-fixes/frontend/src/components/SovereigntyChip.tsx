import { useState } from "react"
import { NetworkTracePanel } from "./NetworkTracePanel"
import { Tooltip } from "./Tooltip"

// The signature element: an always-visible proof of the product's core
// claim (zero external network calls), baked into chrome rather than a
// separate monitoring screen. Present in every state, every screen.
// Clicking it expands a network activity panel (currently illustrative
// sample data -- see NetworkTracePanel).
export function SovereigntyChip() {
  const [panelOpen, setPanelOpen] = useState(false)

  return (
    <div className="relative">
      <Tooltip label="View network activity">
        <button
          type="button"
          onClick={() => setPanelOpen((v) => !v)}
          className="flex items-center gap-2 rounded-full border border-white/10 bg-slate-ember px-3 py-1.5 text-xs text-ash transition-colors hover:bg-slate-ember-hover active:scale-95"
          aria-haspopup="dialog"
          aria-expanded={panelOpen}
        >
          <span className="status-dot h-1.5 w-1.5 rounded-full bg-ember" aria-hidden="true" />
          <span className="font-mono tracking-tight">offline · 0 external calls</span>
        </button>
      </Tooltip>
      {panelOpen && <NetworkTracePanel onClose={() => setPanelOpen(false)} />}
    </div>
  )
}

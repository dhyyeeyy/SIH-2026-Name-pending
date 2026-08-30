// The signature element: an always-visible proof of the product's core
// claim (zero external network calls), baked into chrome rather than a
// separate monitoring screen. Present in every state, every screen.
export function SovereigntyChip() {
  return (
    <div className="flex items-center gap-2 rounded-full border border-white/10 bg-slate-ember px-3 py-1.5 text-xs text-ash">
      <span className="status-dot h-1.5 w-1.5 rounded-full bg-ember" aria-hidden="true" />
      <span className="font-mono tracking-tight">offline · 0 external calls</span>
    </div>
  )
}

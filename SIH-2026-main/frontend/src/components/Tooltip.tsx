import type { ReactNode } from "react"

interface TooltipProps {
  label: string
  children: ReactNode
}

// CSS-only floating label: no positioning library, relies on the
// trigger being a single relatively-sized inline element. Shows on
// hover and on keyboard focus (group-focus-within), so it doesn't
// depend on a mouse to be discoverable.
export function Tooltip({ label, children }: TooltipProps) {
  return (
    <span className="group/tooltip relative inline-flex">
      {children}
      <span
        role="tooltip"
        className="pointer-events-none absolute -top-9 left-1/2 z-50 -translate-x-1/2 translate-y-1 whitespace-nowrap rounded-md border border-white/10 bg-slate-ember px-2.5 py-1 text-xs text-bone opacity-0 shadow-lg transition-all duration-150 group-hover/tooltip:translate-y-0 group-hover/tooltip:opacity-100 group-focus-within/tooltip:translate-y-0 group-focus-within/tooltip:opacity-100"
      >
        {label}
      </span>
    </span>
  )
}

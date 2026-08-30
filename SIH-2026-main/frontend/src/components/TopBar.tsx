import { CodeIcon } from "./icons"
import { SovereigntyChip } from "./SovereigntyChip"

interface TopBarProps {
  title: string
  hasCanvas?: boolean
  canvasOpen?: boolean
  onToggleCanvas?: () => void
}

export function TopBar({ title, hasCanvas, canvasOpen, onToggleCanvas }: TopBarProps) {
  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-white/10 px-4">
      <span className="truncate text-sm text-ash">{title}</span>
      <div className="flex items-center gap-2">
        {hasCanvas && (
          <button
            type="button"
            onClick={onToggleCanvas}
            className={`pop-enter flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs transition-all active:scale-95 focus-visible:outline focus-visible:outline-2 focus-visible:outline-ember ${
              canvasOpen
                ? "border-ember/40 bg-ember-bg text-ember"
                : "border-white/10 text-ash hover:bg-white/5 hover:text-bone"
            }`}
            aria-pressed={canvasOpen}
          >
            <CodeIcon className="h-3.5 w-3.5" />
            Canvas
          </button>
        )}
        <SovereigntyChip />
      </div>
    </header>
  )
}

import { useEffect, useRef, useState } from "react"
import { CodeIcon } from "./icons"
import { SovereigntyChip } from "./SovereigntyChip"

interface TopBarProps {
  title: string
  onRename?: (newTitle: string) => void
  hasCanvas?: boolean
  canvasOpen?: boolean
  onToggleCanvas?: () => void
}

export function TopBar({ title, onRename, hasCanvas, canvasOpen, onToggleCanvas }: TopBarProps) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(title)
  const inputRef = useRef<HTMLInputElement>(null)

  // Keep the draft in sync when the title changes from outside editing
  // (e.g. switching sessions, or the auto-derived title updating).
  useEffect(() => {
    if (!editing) setDraft(title)
  }, [title, editing])

  useEffect(() => {
    if (editing) {
      inputRef.current?.focus()
      inputRef.current?.select()
    }
  }, [editing])

  function commit() {
    setEditing(false)
    const trimmed = draft.trim()
    if (trimmed && trimmed !== title) onRename?.(trimmed)
    else setDraft(title)
  }

  function cancel() {
    setDraft(title)
    setEditing(false)
  }

  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-white/10 px-4">
      {editing ? (
        <input
          ref={inputRef}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commit}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault()
              commit()
            } else if (e.key === "Escape") {
              e.preventDefault()
              cancel()
            }
          }}
          className="w-full max-w-xs truncate rounded-md border border-ember/40 bg-white/5 px-1.5 py-0.5 -mx-1.5 text-sm text-bone focus:outline-none"
          aria-label="Task name"
        />
      ) : (
        <button
          type="button"
          onClick={() => onRename && setEditing(true)}
          disabled={!onRename}
          className={`truncate rounded-md px-1.5 py-0.5 -mx-1.5 text-left text-sm text-ash transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-ember ${
            onRename ? "hover:bg-white/5 hover:text-bone cursor-text" : "cursor-default"
          }`}
          title={onRename ? "Rename task" : undefined}
        >
          {title}
        </button>
      )}
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

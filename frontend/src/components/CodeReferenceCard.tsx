import { CodeIcon } from "./icons"
import type { CodeSegment } from "../lib/parseCodeBlocks"

interface CodeReferenceCardProps {
  segment: CodeSegment
  isActive: boolean
  onOpen: () => void
}

export function CodeReferenceCard({ segment, isActive, onOpen }: CodeReferenceCardProps) {
  const lineCount = segment.code.split("\n").length

  return (
    <button
      type="button"
      onClick={onOpen}
      className={`flex w-full items-center gap-3 rounded-xl border px-3.5 py-3 text-left transition-all active:scale-[0.98] focus-visible:outline focus-visible:outline-2 focus-visible:outline-ember ${
        isActive ? "border-ember/50 bg-ember-bg" : "border-white/10 bg-obsidian/60 hover:bg-obsidian"
      }`}
    >
      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-slate-ember text-ember">
        <CodeIcon className="h-4 w-4" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm text-bone">
          {segment.language !== "text" ? segment.language : "Code"} · {lineCount} line{lineCount !== 1 ? "s" : ""}
        </span>
        <span className="block text-xs text-ash">Open in canvas</span>
      </span>
    </button>
  )
}

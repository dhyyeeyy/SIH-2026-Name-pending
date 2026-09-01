import { useEffect, useState } from "react"
import { XIcon } from "./icons"
import type { CanvasFile } from "../types/canvas"

interface CodeCanvasProps {
  files: CanvasFile[]
  activeFileId: string
  onSelectFile: (id: string) => void
  onClose: () => void
}

function CopyButton({ code }: { code: string }) {
  const [copied, setCopied] = useState(false)

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(code)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      // Clipboard API unavailable (e.g. insecure context) -- fail quietly,
      // the code is still visible and selectable for manual copy.
    }
  }

  return (
    <button
      type="button"
      onClick={handleCopy}
      className="rounded-md border border-white/10 px-2.5 py-1 text-xs text-ash transition-colors hover:bg-white/5 hover:text-bone active:scale-95 focus-visible:outline focus-visible:outline-2 focus-visible:outline-ember"
    >
      <span key={copied ? "copied" : "copy"} className="pop-enter inline-block">
        {copied ? "Copied" : "Copy"}
      </span>
    </button>
  )
}

export function CodeCanvas({ files, activeFileId, onSelectFile, onClose }: CodeCanvasProps) {
  const activeFile = files.find((f) => f.id === activeFileId) ?? files[0]
  const lineCount = activeFile.code.split("\n").length

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose()
    }
    window.addEventListener("keydown", handleKeyDown)
    return () => window.removeEventListener("keydown", handleKeyDown)
  }, [onClose])

  return (
    <aside className="canvas-enter fixed inset-0 z-40 flex flex-col border-l border-white/10 bg-slate-ember sm:relative sm:inset-auto sm:z-auto sm:w-[420px] sm:shrink-0">
      <div className="flex items-center justify-between gap-2 border-b border-white/10 px-4 py-3">
        <div className="flex items-center gap-2 overflow-hidden">
          <span className="truncate font-mono text-xs text-bone">{activeFile.filename}</span>
          <span className="truncate text-xs text-ash/70">
            {lineCount} line{lineCount !== 1 ? "s" : ""}
            {activeFile.model ? ` · ${activeFile.model}` : ""}
          </span>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <CopyButton code={activeFile.code} />
          <button
            type="button"
            onClick={onClose}
            className="flex h-7 w-7 items-center justify-center rounded-md text-ash transition-colors hover:bg-white/5 hover:text-bone active:scale-90 focus-visible:outline focus-visible:outline-2 focus-visible:outline-ember"
            aria-label="Close canvas"
          >
            <XIcon className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {files.length > 1 && (
        <div className="flex shrink-0 gap-1 overflow-x-auto border-b border-white/10 px-2 py-1.5 [scrollbar-width:thin]">
          {files.map((file) => (
            <button
              key={file.id}
              type="button"
              onClick={() => onSelectFile(file.id)}
              className={`shrink-0 rounded-md px-2.5 py-1 font-mono text-xs transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-ember ${
                file.id === activeFile.id
                  ? "bg-ember-bg text-ember"
                  : "text-ash hover:bg-white/5 hover:text-bone"
              }`}
            >
              {file.filename}
            </button>
          ))}
        </div>
      )}

      <div className="flex-1 overflow-auto p-4">
        <pre className="font-mono text-[13px] leading-relaxed text-bone">
          <code>{activeFile.code}</code>
        </pre>
      </div>
    </aside>
  )
}

import { useEffect, useRef } from "react"
import { DocumentIcon, ImageIcon, PdfIcon } from "./icons"
import type { FileKind } from "../lib/fileKind"

const OPTIONS: { kind: FileKind; label: string; accept: string; icon: typeof ImageIcon }[] = [
  { kind: "image", label: "Photo or scan", accept: "image/png,image/jpeg,image/bmp,image/tiff", icon: ImageIcon },
  { kind: "pdf", label: "PDF", accept: "application/pdf", icon: PdfIcon },
  {
    kind: "document",
    label: "Document",
    accept: ".doc,.docx,.txt,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain",
    icon: DocumentIcon,
  },
]

interface AttachMenuProps {
  onPick: (kind: FileKind, accept: string) => void
  onClose: () => void
}

export function AttachMenu({ onPick, onClose }: AttachMenuProps) {
  const menuRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose()
    }
    function handlePointerDown(e: PointerEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) onClose()
    }
    window.addEventListener("keydown", handleKeyDown)
    window.addEventListener("pointerdown", handlePointerDown)
    return () => {
      window.removeEventListener("keydown", handleKeyDown)
      window.removeEventListener("pointerdown", handlePointerDown)
    }
  }, [onClose])

  return (
    <div
      ref={menuRef}
      role="menu"
      className="pop-enter absolute bottom-full left-0 z-20 mb-2 w-48 overflow-hidden rounded-xl border border-white/10 bg-slate-ember shadow-lg"
    >
      {OPTIONS.map(({ kind, label, accept, icon: Icon }) => (
        <button
          key={kind}
          type="button"
          role="menuitem"
          onClick={() => onPick(kind, accept)}
          className="flex w-full items-center gap-2.5 px-3 py-2.5 text-left text-sm text-bone transition-colors hover:bg-white/5 focus-visible:bg-white/5 focus-visible:outline-none"
        >
          <Icon className="h-4 w-4 text-ash" />
          {label}
        </button>
      ))}
    </div>
  )
}

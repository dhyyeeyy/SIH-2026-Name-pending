import { useEffect, useRef, useState, type KeyboardEvent } from "react"
import { AttachMenu } from "./AttachMenu"
import { DatabaseIcon, DocumentIcon, PdfIcon, PlusIcon, SendIcon, XIcon } from "./icons"
import { Switch } from "./Switch"
import { Tooltip } from "./Tooltip"
import { getFileKind, type FileKind } from "../lib/fileKind"

interface ChatInputProps {
  onSubmit: (query: string, attachments: File[]) => void
  disabled?: boolean
  useRag: boolean
  onToggleRag: () => void
}

export function ChatInput({ onSubmit, disabled, useRag, onToggleRag }: ChatInputProps) {
  const [value, setValue] = useState("")
  const [attachment, setAttachment] = useState<File | null>(null)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [menuOpen, setMenuOpen] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const attachmentKind = attachment ? getFileKind(attachment) : null

  // Object URLs must be revoked or they leak -- swap them out whenever
  // the attachment changes, and on unmount. Only images get a preview;
  // PDFs/documents show an icon instead (see attachmentKind below).
  useEffect(() => {
    if (!attachment || getFileKind(attachment) !== "image") {
      setPreviewUrl(null)
      return
    }
    const url = URL.createObjectURL(attachment)
    setPreviewUrl(url)
    return () => URL.revokeObjectURL(url)
  }, [attachment])

  function autoGrow(el: HTMLTextAreaElement) {
    el.style.height = "auto"
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`
  }

  function handleSubmit() {
    const trimmed = value.trim()
    if (!trimmed || disabled) return
    onSubmit(trimmed, attachment ? [attachment] : [])
    setValue("")
    setAttachment(null)
    if (textareaRef.current) textareaRef.current.style.height = "auto"
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  function handleAttachPick(_kind: FileKind, accept: string) {
    setMenuOpen(false)
    if (fileInputRef.current) {
      fileInputRef.current.accept = accept
      fileInputRef.current.click()
    }
  }

  function handleFilePick(e: React.ChangeEvent<HTMLInputElement>) {
    // Only one attachment is ever processed by the agent (agent.py
    // reads attachments[0]) -- picking a new file replaces rather than
    // adds, so the UI never implies more than one file will be read.
    const file = e.target.files?.[0]
    if (file) setAttachment(file)
    e.target.value = ""
  }

  return (
    <div className="w-full rounded-2xl border border-white/15 bg-slate-ember/40 backdrop-blur-xl transition-shadow duration-300 shadow-[0_20px_50px_-20px_rgba(0,0,0,0.6),inset_0_1px_0_rgba(255,255,255,0.08)] focus-within:shadow-[0_20px_50px_-20px_rgba(0,0,0,0.6),inset_0_1px_0_rgba(255,255,255,0.08),0_0_36px_8px_rgba(217,125,61,0.22)]">
      {attachment && (
        <div className="px-4 pt-3">
          <span className="pop-enter flex w-fit items-center gap-2 rounded-lg border border-white/10 bg-obsidian py-1 pl-1 pr-2.5 text-xs text-ash">
            {attachmentKind === "image" && previewUrl ? (
              <img src={previewUrl} alt="" className="h-6 w-6 rounded object-cover" />
            ) : (
              <span className="flex h-6 w-6 items-center justify-center rounded bg-slate-ember text-ember">
                {attachmentKind === "pdf" ? (
                  <PdfIcon className="h-3.5 w-3.5" />
                ) : (
                  <DocumentIcon className="h-3.5 w-3.5" />
                )}
              </span>
            )}
            {attachment.name}
            <button
              type="button"
              onClick={() => setAttachment(null)}
              className="rounded text-ash transition-colors hover:text-bone active:scale-90 focus-visible:outline-2 focus-visible:outline-ember"
              aria-label={`Remove ${attachment.name}`}
            >
              <XIcon className="h-3 w-3" />
            </button>
          </span>
          {attachmentKind === "document" && (
            <p className="mt-1 text-xs text-ash/60">
              .doc/.docx/.txt files aren't read by the agent yet — attached for reference only.
              Images and PDFs are read in full.
            </p>
          )}
        </div>
      )}
      <div className="flex items-end gap-2 p-3">
        <div className="relative">
          {menuOpen && <AttachMenu onPick={handleAttachPick} onClose={() => setMenuOpen(false)} />}
          <Tooltip label="Attach a file">
            <button
              type="button"
              onClick={() => setMenuOpen((v) => !v)}
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-white/10 text-ash transition-colors hover:bg-white/5 hover:text-bone active:scale-90 focus-visible:outline focus-visible:outline-2 focus-visible:outline-ember"
              aria-label="Attach a file"
              aria-haspopup="menu"
              aria-expanded={menuOpen}
            >
              <PlusIcon className="h-4 w-4" />
            </button>
          </Tooltip>
        </div>
        <Tooltip label={useRag ? "Searching your documents" : "Document search is off"}>
          <div className="flex h-9 shrink-0 items-center gap-1.5 rounded-full border border-white/10 px-2.5">
            <DatabaseIcon className={`h-3.5 w-3.5 transition-colors ${useRag ? "text-ember" : "text-ash"}`} />
            <Switch checked={useRag} onChange={onToggleRag} label="Search your documents" />
          </div>
        </Tooltip>
        <input ref={fileInputRef} type="file" className="hidden" onChange={handleFilePick} />
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => {
            setValue(e.target.value)
            autoGrow(e.target)
          }}
          onKeyDown={handleKeyDown}
          rows={1}
          autoComplete="off"
          placeholder="Ask anything..."
          className="max-h-40 flex-1 resize-none overflow-y-auto bg-transparent py-1.5 text-[15px] text-bone placeholder:text-ash/70 focus:outline-none [scrollbar-width:thin] [scrollbar-color:var(--color-ash)_transparent]"
        />
        <Tooltip label="Send message">
          <button
            type="button"
            onClick={handleSubmit}
            disabled={disabled || !value.trim()}
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-ember text-obsidian transition-all hover:opacity-90 active:scale-90 disabled:opacity-30 disabled:active:scale-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-bone"
            aria-label="Send"
          >
            <SendIcon className="h-4 w-4" />
          </button>
        </Tooltip>
      </div>
    </div>
  )
}

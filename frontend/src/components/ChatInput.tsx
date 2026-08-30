import { useRef, useState, type KeyboardEvent } from "react"
import { DatabaseIcon, PlusIcon, SendIcon, XIcon } from "./icons"
import { Switch } from "./Switch"
import { Tooltip } from "./Tooltip"

interface ChatInputProps {
  onSubmit: (query: string, attachments: File[]) => void
  disabled?: boolean
  useRag: boolean
  onToggleRag: () => void
}

export function ChatInput({ onSubmit, disabled, useRag, onToggleRag }: ChatInputProps) {
  const [value, setValue] = useState("")
  const [attachments, setAttachments] = useState<File[]>([])
  const fileInputRef = useRef<HTMLInputElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  function autoGrow(el: HTMLTextAreaElement) {
    el.style.height = "auto"
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`
  }

  function handleSubmit() {
    const trimmed = value.trim()
    if (!trimmed || disabled) return
    onSubmit(trimmed, attachments)
    setValue("")
    setAttachments([])
    if (textareaRef.current) textareaRef.current.style.height = "auto"
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  function handleFilePick(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? [])
    setAttachments((prev) => [...prev, ...files])
    e.target.value = ""
  }

  function removeAttachment(index: number) {
    setAttachments((prev) => prev.filter((_, i) => i !== index))
  }

  return (
    <div className="w-full rounded-2xl border border-white/10 bg-slate-ember/90 backdrop-blur-sm shadow-[0_20px_50px_-20px_rgba(0,0,0,0.6)]">
      {attachments.length > 0 && (
        <div className="flex flex-wrap gap-2 px-4 pt-3">
          {attachments.map((file, i) => (
            <span
              key={`${file.name}-${i}`}
              className="pop-enter flex items-center gap-1.5 rounded-lg border border-white/10 bg-obsidian px-2.5 py-1 text-xs text-ash"
            >
              {file.name}
              <button
                type="button"
                onClick={() => removeAttachment(i)}
                className="rounded text-ash transition-colors hover:text-bone active:scale-90 focus-visible:outline-2 focus-visible:outline-ember"
                aria-label={`Remove ${file.name}`}
              >
                <XIcon className="h-3 w-3" />
              </button>
            </span>
          ))}
        </div>
      )}
      <div className="flex items-end gap-2 p-3">
        <Tooltip label="Attach an image">
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-white/10 text-ash transition-colors hover:bg-white/5 hover:text-bone active:scale-90 focus-visible:outline focus-visible:outline-2 focus-visible:outline-ember"
            aria-label="Attach an image"
          >
            <PlusIcon className="h-4 w-4" />
          </button>
        </Tooltip>
        <Tooltip label={useRag ? "Searching your documents" : "Document search is off"}>
          <div className="flex h-9 shrink-0 items-center gap-1.5 rounded-full border border-white/10 px-2.5">
            <DatabaseIcon className={`h-3.5 w-3.5 transition-colors ${useRag ? "text-ember" : "text-ash"}`} />
            <Switch checked={useRag} onChange={onToggleRag} label="Search your documents" />
          </div>
        </Tooltip>
        <input
          ref={fileInputRef}
          type="file"
          accept="image/png,image/jpeg,image/bmp,image/tiff"
          multiple
          className="hidden"
          onChange={handleFilePick}
        />
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

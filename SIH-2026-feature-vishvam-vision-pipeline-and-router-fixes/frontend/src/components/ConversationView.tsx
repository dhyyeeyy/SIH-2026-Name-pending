import { useEffect, useRef } from "react"
import { ChatInput } from "./ChatInput"
import { MessageBubble } from "./MessageBubble"
import type { ChatMessage } from "../types/chat"

interface ConversationViewProps {
  messages: ChatMessage[]
  onSubmit: (query: string, attachments: File[]) => void
  pending: boolean
  useRag: boolean
  onToggleRag: () => void
  activeCanvasId?: string | null
  onOpenCanvas: (id: string) => void
}

export function ConversationView({
  messages,
  onSubmit,
  pending,
  useRag,
  onToggleRag,
  activeCanvasId,
  onOpenCanvas,
}: ConversationViewProps) {
  const bottomRef = useRef<HTMLDivElement>(null)
  const lastMessage = messages[messages.length - 1]

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" })
    // Re-run when the last message's own content/pending state changes
    // (e.g. pending -> resolved with a long response), not just when a
    // new message is appended -- otherwise a tall response that grows
    // past the viewport never scrolls into view.
  }, [messages.length, lastMessage?.content, lastMessage?.pending])

  function handleRetry(query: string) {
    onSubmit(query, [])
  }

  return (
    <div className="flex flex-1 flex-col overflow-hidden bg-obsidian">
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto flex max-w-3xl flex-col gap-5 px-6 py-8">
          {messages.map((m) => (
            <MessageBubble
              key={m.id}
              message={m}
              activeCanvasId={activeCanvasId}
              onOpenCanvas={onOpenCanvas}
              onRetry={handleRetry}
            />
          ))}
          <div ref={bottomRef} />
        </div>
      </div>
      <div className="border-t border-white/10 bg-obsidian px-6 py-4">
        <div className="mx-auto max-w-3xl">
          <ChatInput onSubmit={onSubmit} disabled={pending} useRag={useRag} onToggleRag={onToggleRag} />
        </div>
      </div>
    </div>
  )
}

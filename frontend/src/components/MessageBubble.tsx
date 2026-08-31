import { AlertIcon, DocumentIcon, ScanIcon } from "./icons"
import { CodeReferenceCard } from "./CodeReferenceCard"
import { parseCodeBlocks } from "../lib/parseCodeBlocks"
import { extractModel } from "../lib/messageUtils"
import type { ChatMessage } from "../types/chat"
import type { CanvasContent } from "../types/canvas"

interface MessageBubbleProps {
  message: ChatMessage
  activeCanvasId?: string | null
  onOpenCanvas?: (content: CanvasContent) => void
}

function PendingContent({ expectingVision }: { expectingVision?: boolean }) {
  if (expectingVision) {
    return (
      <span className="inline-flex items-center gap-2 text-ash">
        <ScanIcon className="status-dot h-4 w-4 text-ember" />
        <span>Reading document…</span>
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1 text-ash">
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-ash [animation-delay:-0.2s]" />
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-ash [animation-delay:-0.1s]" />
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-ash" />
    </span>
  )
}

export function MessageBubble({ message, activeCanvasId, onOpenCanvas }: MessageBubbleProps) {
  const isUser = message.role === "user"
  const hasNoRagMatch = message.trace?.some(
    (t) => t.step === "rag_retrieval" && t.detail === "0 relevant chunks found",
  )

  const segments =
    !isUser && !message.pending && !message.isError ? parseCodeBlocks(message.content) : null
  const model = extractModel(message)

  return (
    <div className={`message-enter flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div className={`max-w-[75ch] ${isUser ? "" : "w-full"}`}>
        {message.attachmentNames && message.attachmentNames.length > 0 && (
          <div className={`mb-1.5 flex flex-wrap gap-1.5 ${isUser ? "justify-end" : ""}`}>
            {message.attachmentNames.map((name) => (
              <span
                key={name}
                className="flex items-center gap-1.5 rounded-lg border border-white/10 bg-slate-ember px-2 py-1 text-xs text-ash"
              >
                <DocumentIcon className="h-3 w-3" />
                {name}
              </span>
            ))}
          </div>
        )}

        {message.pending || message.isError || !segments ? (
          <div
            className={
              isUser
                ? "rounded-2xl rounded-tr-sm bg-ember px-4 py-2.5 text-[15px] text-obsidian"
                : message.isError
                  ? "flex items-start gap-2 rounded-2xl rounded-tl-sm border border-ember-dim/40 bg-slate-ember px-4 py-2.5 text-[15px] text-bone"
                  : "rounded-2xl rounded-tl-sm bg-slate-ember px-4 py-2.5 text-[15px] text-bone"
            }
          >
            {message.pending ? (
              <PendingContent expectingVision={message.expectingVision} />
            ) : message.isError ? (
              <>
                <AlertIcon className="mt-0.5 h-4 w-4 shrink-0 text-ember" />
                <p className="whitespace-pre-wrap leading-relaxed text-ash">
                  Couldn't complete this request. {message.content}
                </p>
              </>
            ) : (
              <p className="whitespace-pre-wrap leading-relaxed">{message.content}</p>
            )}
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            {segments.map((segment, i) =>
              segment.type === "text" ? (
                <div key={i} className="rounded-2xl rounded-tl-sm bg-slate-ember px-4 py-2.5 text-[15px] text-bone">
                  <p className="whitespace-pre-wrap leading-relaxed">{segment.content}</p>
                </div>
              ) : (
                <CodeReferenceCard
                  key={i}
                  segment={segment}
                  isActive={activeCanvasId === `${message.id}:${i}`}
                  onOpen={() =>
                    onOpenCanvas?.({
                      id: `${message.id}:${i}`,
                      language: segment.language,
                      code: segment.code,
                      model,
                    })
                  }
                />
              ),
            )}
          </div>
        )}

        {hasNoRagMatch && (
          <p className="mt-1.5 px-1 text-xs text-ash/60">No matching documents — answered from general knowledge</p>
        )}
      </div>
    </div>
  )
}

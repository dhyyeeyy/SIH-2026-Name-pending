import { useCallback, useState } from "react"
import { runAgent } from "../api"
import type { KnowledgeDoc } from "../components/Sidebar"
import type { ChatMessage, Session } from "../types/chat"

function newId() {
  return crypto.randomUUID()
}

function truncateTitle(text: string, max = 42): string {
  const clean = text.trim().replace(/\s+/g, " ")
  return clean.length > max ? `${clean.slice(0, max - 1)}…` : clean
}

interface UseAgentChatOptions {
  onMessageResolved?: (message: ChatMessage) => void
}

export function useAgentChat({ onMessageResolved }: UseAgentChatOptions = {}) {
  const [sessions, setSessions] = useState<Session[]>([])
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null)
  const [pending, setPending] = useState(false)
  const [documents, setDocuments] = useState<KnowledgeDoc[]>([])
  const [useRag, setUseRag] = useState(false)

  const activeSession = sessions.find((s) => s.id === activeSessionId) ?? null

  const newTask = useCallback(() => {
    setActiveSessionId(null)
    setUseRag(false)
  }, [])

  const toggleRag = useCallback(() => {
    setUseRag((prev) => !prev)
  }, [])

  const selectSession = useCallback((id: string) => {
    setActiveSessionId(id)
  }, [])

  const submit = useCallback(
    async (query: string, attachments: File[]) => {
      if (!query.trim()) return

      const attachmentNames = attachments.map((file) => file.name)
      const userMessage: ChatMessage = {
        id: newId(),
        role: "user",
        content: query,
        attachmentNames: attachmentNames.length ? attachmentNames : undefined,
      }

      const pendingMessage: ChatMessage = {
        id: newId(),
        role: "assistant",
        content: "",
        pending: true,
        expectingVision: attachmentNames.length > 0,
      }

      const isNewSession = !activeSessionId
      const sessionId = activeSessionId ?? newId()

      setSessions((prev) => {
        const existing = prev.find((s) => s.id === sessionId)

        if (existing) {
          return prev.map((s) =>
            s.id === sessionId ? { ...s, messages: [...s.messages, userMessage, pendingMessage] } : s,
          )
        }

        return [{ id: sessionId, title: truncateTitle(query), messages: [userMessage, pendingMessage] }, ...prev]
      })

      if (isNewSession) {
        setActiveSessionId(sessionId)
      }

      setPending(true)

      try {
        const result = await runAgent({
          query,
          user_id: "demo-user",
          attachments,
          use_rag: useRag,
        })

        const trace = Array.isArray(result.trace) ? result.trace : []
        const wasVisionProcessed = trace.some((step) => step.step === "vision_extraction")

        if (wasVisionProcessed && attachmentNames.length > 0) {
          setDocuments((prev) => {
            const existingNames = new Set(prev.map((doc) => doc.name))
            const additions = attachmentNames
              .filter((name) => !existingNames.has(name))
              .map((name) => ({ name, kind: "image" as const }))

            return additions.length > 0 ? [...prev, ...additions] : prev
          })
        }

        const resolvedMessage: ChatMessage = {
          ...pendingMessage,
          content: result.final_answer || "No response returned from the server.",
          trace,
          pending: false,
          isError: false,
        }

        setSessions((prev) =>
          prev.map((s) =>
            s.id === sessionId
              ? {
                  ...s,
                  messages: s.messages.map((message) => (message.id === pendingMessage.id ? resolvedMessage : message)),
                }
              : s,
          ),
        )

        onMessageResolved?.(resolvedMessage)
      } catch (error) {
        const errorMessage = error instanceof Error ? error.message : "Something went wrong while contacting the backend."

        setSessions((prev) =>
          prev.map((s) =>
            s.id === sessionId
              ? {
                  ...s,
                  messages: s.messages.map((message) =>
                    message.id === pendingMessage.id
                      ? {
                          ...message,
                          content: errorMessage,
                          pending: false,
                          isError: true,
                        }
                      : message,
                  ),
                }
              : s,
          ),
        )
      } finally {
        setPending(false)
      }
    },
    [activeSessionId, onMessageResolved, useRag],
  )

  return {
    sessions: sessions.map((s) => ({ id: s.id, title: s.title })),
    activeSession,
    activeSessionId,
    pending,
    newTask,
    selectSession,
    submit,
    documents,
    useRag,
    toggleRag,
  }
}

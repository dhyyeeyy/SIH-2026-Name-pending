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
  /** Called once a message finishes successfully, so callers (e.g. the
   * canvas panel) can react to the final content without needing to
   * diff session state themselves. */
  onMessageResolved?: (message: ChatMessage) => void
}

export function useAgentChat({ onMessageResolved }: UseAgentChatOptions = {}) {
  const [sessions, setSessions] = useState<Session[]>([])
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null)
  const [pending, setPending] = useState(false)
  const [documents, setDocuments] = useState<KnowledgeDoc[]>([])
  const [useRag, setUseRag] = useState(true)

  const activeSession = sessions.find((s) => s.id === activeSessionId) ?? null

  const newTask = useCallback(() => {
    setActiveSessionId(null)
    setUseRag(true)
  }, [])

  const toggleRag = useCallback(() => {
    setUseRag((prev) => !prev)
  }, [])

  const selectSession = useCallback((id: string) => {
    setActiveSessionId(id)
  }, [])

  const submit = useCallback(
    async (query: string, attachments: File[]) => {
      const attachmentNames = attachments.map((f) => f.name)
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

      // Decide the session id up front (rather than inside the setSessions
      // updater) so the updater stays pure -- React 18 StrictMode
      // double-invokes updater functions in dev to catch exactly this kind
      // of side effect, and a mutated closure variable here caused the
      // whole submit flow to hang unpredictably.
      const isNewSession = !activeSessionId
      const sessionId = activeSessionId ?? newId()

      setSessions((prev) => {
        if (!isNewSession && prev.some((s) => s.id === sessionId)) {
          return prev.map((s) =>
            s.id === sessionId ? { ...s, messages: [...s.messages, userMessage, pendingMessage] } : s,
          )
        }
        const session: Session = {
          id: sessionId,
          title: truncateTitle(query),
          messages: [userMessage, pendingMessage],
        }
        return [session, ...prev]
      })
      if (isNewSession) setActiveSessionId(sessionId)

      setPending(true)
      try {
        const result = await runAgent({ query, user_id: "demo-user", attachments, use_rag: useRag })

        const wasVisionProcessed = result.trace.some((t) => t.step === "vision_extraction")
        if (wasVisionProcessed && attachmentNames.length > 0) {
          setDocuments((prev) => {
            const existing = new Set(prev.map((d) => d.name))
            const additions = attachmentNames.filter((name) => !existing.has(name)).map((name) => ({ name, kind: "image" as const }))
            return additions.length ? [...prev, ...additions] : prev
          })
        }

        const resolvedMessage: ChatMessage = {
          ...pendingMessage,
          content: result.final_answer,
          trace: result.trace,
          pending: false,
        }

        setSessions((prev) =>
          prev.map((s) =>
            s.id === sessionId
              ? { ...s, messages: s.messages.map((m) => (m.id === pendingMessage.id ? resolvedMessage : m)) }
              : s,
          ),
        )
        onMessageResolved?.(resolvedMessage)
      } catch (err) {
        const message = err instanceof Error ? err.message : "Something went wrong."
        setSessions((prev) =>
          prev.map((s) =>
            s.id === sessionId
              ? {
                  ...s,
                  messages: s.messages.map((m) =>
                    m.id === pendingMessage.id
                      ? { ...m, content: message, pending: false, isError: true }
                      : m,
                  ),
                }
              : s,
          ),
        )
      } finally {
        setPending(false)
      }
    },
    [activeSessionId, useRag, onMessageResolved],
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

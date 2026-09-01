import { useCallback, useEffect, useState } from "react"
import { runAgent } from "../api"
import type { KnowledgeDoc } from "../components/Sidebar"
import { getFileKind } from "../lib/fileKind"
import type { ChatMessage, Session } from "../types/chat"

function newId() {
  return crypto.randomUUID()
}

function truncateTitle(text: string, max = 42): string {
  const clean = text.trim().replace(/\s+/g, " ")
  return clean.length > max ? `${clean.slice(0, max - 1)}…` : clean
}

// Per-browser persistence so a page refresh doesn't wipe the whole
// conversation history and knowledge base list -- previously pure
// in-memory React state. Versioned key so a future shape change can
// just bump the suffix instead of needing a migration.
const STORAGE_KEY = "workbench:v2"

interface PersistedState {
  sessions: Session[]
  documents: KnowledgeDoc[]
}

// A message still "pending" in storage means the page was reloaded
// mid-request -- the original in-flight call is gone, so it can never
// resolve. Surface that honestly instead of leaving a permanently
// stuck "..." bubble.
function sanitizeSessions(sessions: Session[]): Session[] {
  return sessions.map((s) => ({
    ...s,
    messages: s.messages.map((m) =>
      m.pending
        ? { ...m, pending: false, isError: true, content: "Interrupted by a page reload." }
        : m,
    ),
  }))
}

function loadPersisted(): PersistedState {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return { sessions: [], documents: [] }
    const parsed = JSON.parse(raw)
    return {
      sessions: Array.isArray(parsed.sessions) ? sanitizeSessions(parsed.sessions) : [],
      documents: Array.isArray(parsed.documents) ? parsed.documents : [],
    }
  } catch {
    // Private browsing, corrupted data, storage disabled -- start fresh
    // rather than crash the app over persistence.
    return { sessions: [], documents: [] }
  }
}

interface UseAgentChatOptions {
  /** Called once a message finishes successfully, so callers (e.g. the
   * canvas panel) can react to the final content without needing to
   * diff session state themselves. */
  onMessageResolved?: (message: ChatMessage) => void
}

export function useAgentChat({ onMessageResolved }: UseAgentChatOptions = {}) {
  const [sessions, setSessions] = useState<Session[]>(() => loadPersisted().sessions)
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null)
  const [pending, setPending] = useState(false)
  const [documents, setDocuments] = useState<KnowledgeDoc[]>(() => loadPersisted().documents)
  const [useRag, setUseRag] = useState(true)

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ sessions, documents }))
    } catch {
      // Storage full or unavailable -- persistence is a convenience,
      // not a requirement, so fail silently rather than break the app.
    }
  }, [sessions, documents])

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

  // User-driven rename (top bar) -- overrides the auto-derived title from
  // the first query. Sidebar reads the same `sessions` state, so it picks
  // up the new title for free, no separate sync needed.
  const renameSession = useCallback((id: string, title: string) => {
    const trimmed = truncateTitle(title, 60)
    if (!trimmed) return
    setSessions((prev) => prev.map((s) => (s.id === id ? { ...s, title: trimmed } : s)))
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
        // Only images actually go through vision extraction -- showing
        // "Reading document..." for a PDF/doc attachment would imply
        // it's being read when agent.py has no path for that yet.
        expectingVision: attachments.length > 0 && getFileKind(attachments[0]) === "image",
        retryQuery: query,
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

        // Every attachment that was actually sent belongs in the
        // Knowledge Base list, not just the ones the agent could
        // process -- omitting PDFs/documents made it look like the
        // upload silently vanished. "indexed" tracks whether it's
        // genuinely searchable (only true for images that went through
        // vision extraction today); anything else is still listed, just
        // marked as not yet searchable rather than hidden.
        if (attachments.length > 0) {
          const wasVisionProcessed = result.trace.some((t) => t.step === "vision_extraction")
          const file = attachments[0]
          const kind = getFileKind(file)
          setDocuments((prev) => {
            const existing = new Set(prev.map((d) => d.name))
            if (existing.has(file.name)) return prev
            return [...prev, { name: file.name, kind, indexed: wasVisionProcessed }]
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
    renameSession,
    submit,
    documents,
    useRag,
    toggleRag,
  }
}

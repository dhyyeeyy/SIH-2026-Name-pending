import { useCallback, useState } from "react"
import { CodeCanvas } from "./components/CodeCanvas"
import { ConversationView } from "./components/ConversationView"
import { EmptyStateHero } from "./components/EmptyStateHero"
import { Sidebar } from "./components/Sidebar"
import { TopBar } from "./components/TopBar"
import { useAgentChat } from "./hooks/useAgentChat"
import { extractModel } from "./lib/messageUtils"
import { parseCodeBlocks } from "./lib/parseCodeBlocks"
import type { CanvasContent } from "./types/canvas"
import type { ChatMessage } from "./types/chat"

function App() {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(
    () => typeof window !== "undefined" && window.innerWidth < 640,
  )
  const [canvasContent, setCanvasContent] = useState<CanvasContent | null>(null)
  const [canvasOpen, setCanvasOpen] = useState(false)

  const openCanvas = useCallback((content: CanvasContent) => {
    setCanvasContent(content)
    setCanvasOpen(true)
  }, [])

  // Code is meant to land in the canvas, not sit as inline chat text --
  // auto-open on the first code block of a freshly resolved response.
  const handleMessageResolved = useCallback(
    (message: ChatMessage) => {
      const segments = parseCodeBlocks(message.content)
      const firstCodeIndex = segments.findIndex((s) => s.type === "code")
      if (firstCodeIndex === -1) return
      const segment = segments[firstCodeIndex]
      if (segment.type !== "code") return
      openCanvas({
        id: `${message.id}:${firstCodeIndex}`,
        language: segment.language,
        code: segment.code,
        model: extractModel(message),
      })
    },
    [openCanvas],
  )

  const {
    sessions,
    activeSession,
    activeSessionId,
    pending,
    newTask,
    selectSession,
    submit,
    documents,
    useRag,
    toggleRag,
  } = useAgentChat({ onMessageResolved: handleMessageResolved })

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-obsidian text-bone">
      <Sidebar
        collapsed={sidebarCollapsed}
        onToggle={() => setSidebarCollapsed((v) => !v)}
        sessions={sessions}
        activeSessionId={activeSessionId}
        onSelectSession={selectSession}
        onNewTask={newTask}
        documents={documents}
      />
      <div className="flex flex-1 flex-col overflow-hidden">
        <TopBar
          title={activeSession?.title ?? "New task"}
          hasCanvas={!!canvasContent}
          canvasOpen={canvasOpen}
          onToggleCanvas={() => setCanvasOpen((v) => !v)}
        />
        {activeSession ? (
          <ConversationView
            messages={activeSession.messages}
            onSubmit={submit}
            pending={pending}
            useRag={useRag}
            onToggleRag={toggleRag}
            activeCanvasId={canvasOpen ? canvasContent?.id : null}
            onOpenCanvas={openCanvas}
          />
        ) : (
          <EmptyStateHero onSubmit={submit} useRag={useRag} onToggleRag={toggleRag} />
        )}
      </div>
      {canvasOpen && canvasContent && (
        <CodeCanvas content={canvasContent} onClose={() => setCanvasOpen(false)} />
      )}
    </div>
  )
}

export default App

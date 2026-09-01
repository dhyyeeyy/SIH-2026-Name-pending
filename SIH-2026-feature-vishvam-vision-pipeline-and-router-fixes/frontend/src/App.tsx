import { useCallback, useMemo, useState } from "react"
import { CodeCanvas } from "./components/CodeCanvas"
import { ConversationView } from "./components/ConversationView"
import { EmptyStateHero } from "./components/EmptyStateHero"
import { Sidebar } from "./components/Sidebar"
import { TopBar } from "./components/TopBar"
import { useAgentChat } from "./hooks/useAgentChat"
import { deriveCanvasFiles } from "./lib/canvasFiles"
import type { ChatMessage } from "./types/chat"

function App() {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(
    () => typeof window !== "undefined" && window.innerWidth < 640,
  )
  const [canvasOpen, setCanvasOpen] = useState(false)
  const [activeCanvasFileId, setActiveCanvasFileId] = useState<string | null>(null)

  const openCanvas = useCallback((id: string) => {
    setActiveCanvasFileId(id)
    setCanvasOpen(true)
  }, [])

  // Code is meant to land in the canvas, not sit as inline chat text --
  // auto-open on the first code block of a freshly resolved response.
  const handleMessageResolved = useCallback(
    (message: ChatMessage) => {
      const files = deriveCanvasFiles([message])
      if (files.length > 0) openCanvas(files[0].id)
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
    renameSession,
    submit,
    documents,
    useRag,
    toggleRag,
  } = useAgentChat({ onMessageResolved: handleMessageResolved })

  // Derived from the active session's message history, not tracked as
  // separate mutable state -- every code block ever produced in this
  // session, in order, browsable like files rather than a single
  // anonymous snippet. Recomputes for free on session switch.
  const canvasFiles = useMemo(
    () => (activeSession ? deriveCanvasFiles(activeSession.messages) : []),
    [activeSession],
  )

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
          onRename={activeSessionId ? (title) => renameSession(activeSessionId, title) : undefined}
          hasCanvas={canvasFiles.length > 0}
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
            activeCanvasId={canvasOpen ? activeCanvasFileId : null}
            onOpenCanvas={openCanvas}
          />
        ) : (
          <EmptyStateHero onSubmit={submit} useRag={useRag} onToggleRag={toggleRag} />
        )}
      </div>
      {canvasOpen && canvasFiles.length > 0 && (
        <CodeCanvas
          files={canvasFiles}
          activeFileId={activeCanvasFileId ?? canvasFiles[0].id}
          onSelectFile={setActiveCanvasFileId}
          onClose={() => setCanvasOpen(false)}
        />
      )}
    </div>
  )
}

export default App

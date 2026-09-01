import { useEffect } from "react"
import { DocumentIcon, ImageIcon, PdfIcon, PlusIcon, SidebarToggleIcon } from "./icons"
import { Tooltip } from "./Tooltip"
import type { FileKind } from "../lib/fileKind"

export interface SessionSummary {
  id: string
  title: string
}

export interface KnowledgeDoc {
  name: string
  kind: FileKind
  /** True only for documents actually embedded into the RAG store
   * (currently: images that went through vision extraction). PDFs and
   * other documents are listed here too since they were genuinely
   * attached, but agent.py has no ingestion path for them yet -- shown
   * as not searchable rather than silently omitted. */
  indexed: boolean
}

const KIND_ICON: Record<FileKind, typeof DocumentIcon> = {
  image: ImageIcon,
  pdf: PdfIcon,
  document: DocumentIcon,
}

interface SidebarProps {
  collapsed: boolean
  onToggle: () => void
  sessions: SessionSummary[]
  activeSessionId: string | null
  onSelectSession: (id: string) => void
  onNewTask: () => void
  documents: KnowledgeDoc[]
}

export function Sidebar({
  collapsed,
  onToggle,
  sessions,
  activeSessionId,
  onSelectSession,
  onNewTask,
  documents,
}: SidebarProps) {
  useEffect(() => {
    if (collapsed) return
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onToggle()
    }
    window.addEventListener("keydown", handleKeyDown)
    return () => window.removeEventListener("keydown", handleKeyDown)
  }, [collapsed, onToggle])

  return (
    <>
      {!collapsed && (
        <div
          className="fixed inset-0 z-30 bg-black/50 sm:hidden"
          onClick={onToggle}
          aria-hidden="true"
        />
      )}
      <aside
        className={`flex h-full shrink-0 flex-col border-r border-white/10 bg-slate-ember transition-[width] duration-200 ${
          collapsed
            ? "w-14"
            : "drawer-enter fixed inset-y-0 left-0 z-40 w-64 sm:relative sm:inset-auto sm:z-auto"
        }`}
      >
      <div className="flex items-center gap-2 p-3">
        <Tooltip label={collapsed ? "Expand sidebar" : "Collapse sidebar"}>
          <button
            type="button"
            onClick={onToggle}
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-ash transition-colors hover:bg-white/5 hover:text-bone active:scale-90 focus-visible:outline focus-visible:outline-2 focus-visible:outline-ember"
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            aria-expanded={!collapsed}
          >
            <SidebarToggleIcon className="h-4 w-4" />
          </button>
        </Tooltip>
        {!collapsed && <span className="font-display text-sm italic text-bone">Workbench</span>}
      </div>

      <div className="px-2">
        <button
          type="button"
          onClick={onNewTask}
          className={`flex w-full items-center gap-2 rounded-lg border border-white/10 px-2.5 py-2 text-sm text-bone transition-colors hover:bg-white/5 active:scale-[0.98] focus-visible:outline focus-visible:outline-2 focus-visible:outline-ember ${
            collapsed ? "justify-center" : ""
          }`}
        >
          <PlusIcon className="h-4 w-4 shrink-0" />
          {!collapsed && <span>New task</span>}
        </button>
      </div>

      {!collapsed && (
        <div className="mt-6 flex-1 space-y-6 overflow-y-auto px-3 pb-3">
          <div>
            <p className="px-1 pb-2 font-mono text-[11px] uppercase tracking-wider text-ash/70">Recent</p>
            {sessions.length === 0 ? (
              <p className="px-1 text-xs text-ash/60">No tasks yet</p>
            ) : (
              <ul className="space-y-0.5">
                {sessions.map((s) => (
                  <li key={s.id}>
                    <button
                      type="button"
                      onClick={() => onSelectSession(s.id)}
                      className={`w-full truncate rounded-lg px-2 py-1.5 text-left text-sm transition-colors hover:bg-white/5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-ember ${
                        s.id === activeSessionId ? "bg-white/5 text-bone" : "text-ash"
                      }`}
                      title={s.title}
                    >
                      {s.title}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div>
            <p className="px-1 pb-2 font-mono text-[11px] uppercase tracking-wider text-ash/70">Knowledge base</p>
            {documents.length === 0 ? (
              <p className="px-1 text-xs text-ash/60">No documents ingested yet</p>
            ) : (
              <ul className="space-y-0.5">
                {documents.map((doc) => {
                  const Icon = KIND_ICON[doc.kind]
                  return (
                    <li key={doc.name} className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-sm text-ash">
                      <Icon className="h-3.5 w-3.5 shrink-0 text-ash/70" />
                      <span className="min-w-0 flex-1 truncate" title={doc.name}>
                        {doc.name}
                      </span>
                      {!doc.indexed && (
                        <span className="shrink-0 text-[10px] text-ash/50" title="Not yet searchable via document search">
                          not indexed
                        </span>
                      )}
                    </li>
                  )
                })}
              </ul>
            )}
          </div>
        </div>
      )}
      </aside>
    </>
  )
}

// Mirrors agent/agent.py's AgentResult contract exactly. If that
// contract ever changes, this is the one place to update on the
// frontend side.

export type TraceStep =
  | "router_decision"
  | "rag_retrieval"
  | "rag_skipped"
  | "vision_extraction"
  | "vision_extraction_failed"
  | "image_downscaled"
  | "rag_ingest"
  | "model_response"
  | "failed"

export interface RouterDecisionDetail {
  role: "general" | "code" | "vision"
  confidence: number
  override: boolean
}

export interface TraceEntry {
  step: TraceStep
  detail: RouterDecisionDetail | string
}

export interface FileToGenerate {
  type: "docx" | "pptx" | "xlsx"
  title: string
  content: unknown
}

export interface AgentResult {
  final_answer: string
  trace: TraceEntry[]
  files_to_generate: FileToGenerate[] | null
}

export interface AgentRequest {
  query: string
  user_id: string
  attachments?: File[]
  use_rag?: boolean
}

// Real client for Dharm's FastAPI backend, once it exists. Endpoint
// path/shape is a guess based on agent.run()'s contract -- confirm
// with Dharm and adjust when the backend actually lands.

import type { AgentRequest, AgentResult } from "../types/agent"

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000"

export async function realRun({ query, user_id, attachments, use_rag = false }: AgentRequest): Promise<AgentResult> {
  const formData = new FormData()
  formData.append("query", query)
  formData.append("user_id", user_id)
  formData.append("use_rag", String(use_rag))
  for (const file of attachments ?? []) {
    formData.append("attachments", file)
  }

  const response = await fetch(`${API_BASE}/api/agent/run`, {
    method: "POST",
    body: formData,
  })

  if (!response.ok) {
    const text = await response.text()
    throw new Error(`Agent request failed: ${response.status} ${response.statusText} ${text}`)
  }

  const data = await response.json()
  return {
    final_answer: data.final_answer ?? data.answer ?? "",
    trace: Array.isArray(data.trace) ? data.trace : [],
    files_to_generate: data.files_to_generate ?? null,
  }
}

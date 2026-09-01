// Real client for Dharm's FastAPI backend (backend/main.py in this repo).
// Confirmed against the actual running service, not guessed: field
// names, endpoint path, and default port (8000) all matched what was
// originally assumed here, which is a genuinely lucky coincidence, not
// something to rely on if his contract ever shifts.

import type { AgentRequest, AgentResult } from "../types/agent"

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000"

// The backend's own shape -- broader than our AgentResult, and
// final_answer can genuinely be null on its error path (main.py's
// exception handler returns {"final_answer": null, "trace": [],
// "error": true, ...} with HTTP 500, not just a bare error page).
interface BackendResponse {
  final_answer: string | null
  trace: unknown
  files_to_generate: unknown
  handled_by?: string
  error?: boolean
  raw?: { generated_code?: string }
}

// For a code-routed query, final_answer is only a status line ("Code
// ran successfully...") -- the actual generated code lives in
// raw.generated_code, a field the backend's own documented contract
// doesn't mention. The code genuinely exists and genuinely ran; this
// just reformats it as a fenced block so the canvas panel (which
// parses fenced code out of final_answer) picks it up, same as the
// mock and our own agent.py already produce. Not fabricating
// anything -- surfacing data that's really there but not where the
// rest of the UI looks for it.
function withCodeFence(body: BackendResponse): string {
  const answer = body.final_answer ?? ""
  const code = body.raw?.generated_code
  if (body.handled_by !== "code" || !code || answer.includes("```")) return answer
  return `${answer}\n\n\`\`\`python\n${code}\n\`\`\``
}

export async function realRun({ query, user_id, attachments, use_rag = true }: AgentRequest): Promise<AgentResult> {
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

  let body: BackendResponse
  try {
    body = await response.json()
  } catch {
    // Not JSON at all -- e.g. a 404 HTML page from a wrong endpoint
    // path, or the server not running. This is the one case where the
    // HTTP status is the only signal we have.
    throw new Error(`Agent request failed: ${response.status} ${response.statusText}`)
  }

  // The backend returns HTTP 500 with a real, human-readable error
  // message in final_answer (not just a generic status) -- surface
  // that instead of a bare "500 Internal Server Error", so it lands in
  // the same error-bubble + retry UI as a mock-simulated failure.
  if (!response.ok || body.error) {
    throw new Error(body.final_answer ?? `Agent request failed: ${response.status} ${response.statusText}`)
  }

  return {
    final_answer: withCodeFence(body),
    trace: Array.isArray(body.trace) ? (body.trace as AgentResult["trace"]) : [],
    files_to_generate: Array.isArray(body.files_to_generate)
      ? (body.files_to_generate as AgentResult["files_to_generate"])
      : null,
  }
}

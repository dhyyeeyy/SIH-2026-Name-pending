// Single switch point: flip VITE_USE_MOCK_API=false in .env once
// Dharm's backend is live. Every component should import `runAgent`
// from here, never the mock/real clients directly.

import { mockRun } from "./mockAgentClient"
import { realRun } from "./realAgentClient"
import type { AgentRequest, AgentResult } from "../types/agent"

const useMock = import.meta.env.VITE_USE_MOCK_API === "true"

export function runAgent(request: AgentRequest): Promise<AgentResult> {
  return useMock ? mockRun(request) : realRun(request)
}

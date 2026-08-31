// Stands in for Dharm's not-yet-built FastAPI backend. Mirrors the
// exact shape and step sequence agent/agent.py's run() actually
// produces (verified against real runs during backend development),
// so swapping this for a real HTTP call later requires no UI changes
// -- only api/index.ts's export needs to change.

import type { AgentRequest, AgentResult, TraceEntry } from "../types/agent"

const CODE_KEYWORDS = ["function", "code", "script", "python", "write a", "bug", "refactor"]
const IMAGE_EXTENSIONS = [".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif"]

function delay(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function classify(query: string, hasImage: boolean): "general" | "code" | "vision" {
  if (hasImage) return "vision"
  const lower = query.toLowerCase()
  if (CODE_KEYWORDS.some((kw) => lower.includes(kw))) return "code"
  return "general"
}

export async function mockRun({ query, attachments, use_rag = false }: AgentRequest): Promise<AgentResult> {
  // Manual escape hatches for exercising states that are rare/hard to
  // trigger organically from the real backend during dev.
  const lowerQuery = query.toLowerCase()
  if (lowerQuery.includes("simulate error")) {
    await delay(500)
    throw new Error("The model didn't respond in time. This is a simulated failure for UI testing.")
  }
  const forceNoMatch = lowerQuery.includes("no rag match")

  const hasImage = !!attachments?.some((f) =>
    IMAGE_EXTENSIONS.some((ext) => f.name.toLowerCase().endsWith(ext)),
  )
  const role = classify(query, hasImage)
  const trace: TraceEntry[] = []

  trace.push({
    step: "router_decision",
    detail: { role, confidence: 0.55 + Math.random() * 0.3, override: hasImage },
  })
  await delay(300)

  if (role !== "vision" && !use_rag) {
    trace.push({ step: "rag_skipped", detail: "disabled by user" })
  }

  let finalAnswer: string

  if (role === "vision") {
    trace.push({ step: "image_downscaled", detail: "resized to max 1280px" })
    await delay(600)
    trace.push({ step: "vision_extraction", detail: "model=qwen3.5:2b" })
    await delay(900)
    trace.push({ step: "rag_ingest", detail: `stored summary + raw_ocr for ${attachments?.[0]?.name}` })
    finalAnswer =
      "Based on the attached document: the inspection notes minor corrosion on the primary valve and recommends seal replacement within 30 days. (mock response -- real backend not yet connected)"
  } else if (role === "code") {
    if (use_rag) {
      trace.push({ step: "rag_retrieval", detail: forceNoMatch ? "0 relevant chunks found" : "1 chunks retrieved" })
    }
    await delay(700)
    finalAnswer =
      "Here's a reversible string utility with a couple of edge cases handled:\n\n" +
      "```python\n" +
      "def reverse_string(s: str) -> str:\n" +
      '    """Reverse a string, safe for empty input."""\n' +
      "    if not s:\n" +
      "        return s\n" +
      "    return s[::-1]\n\n\n" +
      "def is_palindrome(s: str) -> bool:\n" +
      "    normalized = s.lower().replace(\" \", \"\")\n" +
      "    return normalized == reverse_string(normalized)\n" +
      "```\n\n" +
      "The palindrome check reuses `reverse_string` rather than duplicating the slice logic. " +
      "(mock response -- real backend not yet connected)"
  } else if (use_rag) {
    trace.push({ step: "rag_retrieval", detail: forceNoMatch ? "0 relevant chunks found" : "3 chunks retrieved" })
    await delay(700)
    finalAnswer = forceNoMatch
      ? "I couldn't find anything in your documents about this, so here's a general answer instead: this depends on the specific context, but typically the standard approach applies. (mock response -- real backend not yet connected)"
      : "According to the retrieved documents, the recommended action should be completed within the stated timeframe. (mock response -- real backend not yet connected)"
  } else {
    await delay(700)
    finalAnswer =
      "Here's a general answer without consulting your documents: this depends on the specific context, but typically the standard approach applies. (mock response -- real backend not yet connected)"
  }

  trace.push({ step: "model_response", detail: `model=${role === "code" ? "qwen2.5-coder:3b" : "qwen3:1.7b"}` })

  return {
    final_answer: finalAnswer,
    trace,
    files_to_generate: null,
  }
}

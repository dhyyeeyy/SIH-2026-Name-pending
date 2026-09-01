import type { ChatMessage } from "../types/chat"

export function extractModel(message: ChatMessage): string | undefined {
  const entry = message.trace?.find((t) => t.step === "model_response")
  if (entry && typeof entry.detail === "string") {
    return entry.detail.replace(/^model=/, "")
  }
  return undefined
}

import type { TraceEntry } from "./agent"

export interface ChatMessage {
  id: string
  role: "user" | "assistant"
  content: string
  attachmentNames?: string[]
  trace?: TraceEntry[]
  pending?: boolean
  expectingVision?: boolean
  isError?: boolean
  /** The original query text, carried onto the assistant message so a
   * failed response can offer a "Retry" action without the caller
   * needing to look up the paired user message. Attachments aren't
   * retried -- the raw File isn't retained past the original send. */
  retryQuery?: string
}

export interface Session {
  id: string
  title: string
  messages: ChatMessage[]
}

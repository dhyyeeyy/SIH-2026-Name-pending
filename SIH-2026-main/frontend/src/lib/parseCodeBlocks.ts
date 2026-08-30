export interface TextSegment {
  type: "text"
  content: string
}

export interface CodeSegment {
  type: "code"
  language: string
  code: string
}

export type ContentSegment = TextSegment | CodeSegment

const FENCE_RE = /```(\w*)\n([\s\S]*?)```/g

/**
 * Split a message's raw content into alternating text/code segments by
 * parsing markdown-style fenced code blocks. Used so code can be moved
 * into the canvas panel instead of rendered inline with literal
 * backticks in the chat bubble.
 */
export function parseCodeBlocks(content: string): ContentSegment[] {
  const segments: ContentSegment[] = []
  let lastIndex = 0

  for (const match of content.matchAll(FENCE_RE)) {
    const [full, language, code] = match
    const start = match.index ?? 0

    if (start > lastIndex) {
      const text = content.slice(lastIndex, start).trim()
      if (text) segments.push({ type: "text", content: text })
    }

    segments.push({ type: "code", language: language || "text", code: code.trim() })
    lastIndex = start + full.length
  }

  if (lastIndex < content.length) {
    const text = content.slice(lastIndex).trim()
    if (text) segments.push({ type: "text", content: text })
  }

  if (segments.length === 0) {
    segments.push({ type: "text", content })
  }

  return segments
}

export function hasCodeBlock(content: string): boolean {
  return /```\w*\n[\s\S]*?```/.test(content)
}

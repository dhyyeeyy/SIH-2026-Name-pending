import { parseCodeBlocks } from "./parseCodeBlocks"
import { extractModel } from "./messageUtils"
import type { ChatMessage } from "../types/chat"
import type { CanvasFile } from "../types/canvas"

const LANGUAGE_EXTENSIONS: Record<string, string> = {
  python: "py",
  py: "py",
  javascript: "js",
  js: "js",
  jsx: "jsx",
  typescript: "ts",
  ts: "ts",
  tsx: "tsx",
  json: "json",
  bash: "sh",
  sh: "sh",
  shell: "sh",
  html: "html",
  css: "css",
  sql: "sql",
  java: "java",
  c: "c",
  cpp: "cpp",
  "c++": "cpp",
  go: "go",
  rust: "rs",
  rs: "rs",
  ruby: "rb",
  rb: "rb",
  php: "php",
  yaml: "yml",
  yml: "yml",
  markdown: "md",
  md: "md",
}

function extensionFor(language: string): string {
  return LANGUAGE_EXTENSIONS[language.toLowerCase()] ?? "txt"
}

/**
 * Every code block across a session's messages, in chronological order,
 * treated as a "file" the way Claude Code's own file view would --
 * models don't emit real filenames in fenced blocks, so names are
 * synthesized (snippet_1.py, snippet_2.js, ...) rather than left
 * anonymous. Derived from message history rather than tracked as
 * separate mutable state, so switching sessions or replaying history
 * never needs manual sync.
 */
export function deriveCanvasFiles(messages: ChatMessage[]): CanvasFile[] {
  const files: CanvasFile[] = []
  let counter = 0

  for (const message of messages) {
    if (message.role !== "assistant" || message.pending || message.isError) continue
    const segments = parseCodeBlocks(message.content)
    const model = extractModel(message)

    segments.forEach((segment, i) => {
      if (segment.type !== "code") return
      counter += 1
      files.push({
        id: `${message.id}:${i}`,
        filename: `snippet_${counter}.${extensionFor(segment.language)}`,
        language: segment.language,
        code: segment.code,
        model,
      })
    })
  }

  return files
}

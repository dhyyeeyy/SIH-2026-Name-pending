import type { NetworkEvent } from "../types/network"

// Illustrative sample data ONLY -- not a real capture. True packet-level
// tracing needs OS-level network access a browser fundamentally cannot
// have; the real system-wide monitor is a separate, backend-driven
// piece of the project. This exists so the UI design is ready to wire
// to a real event feed later, without ever being mistaken for one now.
const SAMPLE_POOL: Omit<NetworkEvent, "id" | "time">[] = [
  { protocol: "HTTP", destination: "127.0.0.1:11434", label: "ollama · qwen3:1.7b" },
  { protocol: "HTTP", destination: "127.0.0.1:11434", label: "ollama · qwen2.5-coder:3b" },
  { protocol: "HTTP", destination: "127.0.0.1:11434", label: "ollama · qwen3.5:2b" },
  { protocol: "HTTP", destination: "127.0.0.1:11434", label: "ollama · nomic-embed-text" },
  { protocol: "IPC", destination: "localhost:5173", label: "frontend dev server" },
  { protocol: "HTTP", destination: "127.0.0.1:8000", label: "agent API (planned)" },
]

function formatTime(): string {
  return new Date().toLocaleTimeString(undefined, { hour12: false })
}

export function generateSampleEvent(): NetworkEvent {
  const sample = SAMPLE_POOL[Math.floor(Math.random() * SAMPLE_POOL.length)]
  return {
    id: crypto.randomUUID(),
    time: formatTime(),
    ...sample,
  }
}

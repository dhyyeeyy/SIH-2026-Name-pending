import { useEffect, useRef, useState } from "react"
import { generateSampleEvent } from "../lib/mockNetworkTrace"
import type { NetworkEvent } from "../types/network"

interface NetworkTracePanelProps {
  onClose: () => void
}

const MAX_ROWS = 12
const TICK_MS = 2200

export function NetworkTracePanel({ onClose }: NetworkTracePanelProps) {
  const [events, setEvents] = useState<NetworkEvent[]>(() => [generateSampleEvent()])
  const panelRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const interval = setInterval(() => {
      setEvents((prev) => [generateSampleEvent(), ...prev].slice(0, MAX_ROWS))
    }, TICK_MS)
    return () => clearInterval(interval)
  }, [])

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose()
    }
    function handlePointerDown(e: PointerEvent) {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) onClose()
    }
    window.addEventListener("keydown", handleKeyDown)
    window.addEventListener("pointerdown", handlePointerDown)
    return () => {
      window.removeEventListener("keydown", handleKeyDown)
      window.removeEventListener("pointerdown", handlePointerDown)
    }
  }, [onClose])

  return (
    <div
      ref={panelRef}
      className="pop-enter absolute right-0 top-full z-30 mt-2 w-80 overflow-hidden rounded-xl border border-white/10 bg-slate-ember shadow-xl sm:w-96"
    >
      <div className="flex items-center justify-between border-b border-white/10 px-3.5 py-2.5">
        <span className="text-sm text-bone">Network activity</span>
        <span className="rounded-full border border-ember/30 bg-ember-bg px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-ember">
          Sample data
        </span>
      </div>
      <p className="border-b border-white/10 px-3.5 py-2 text-xs text-ash/70">
        Illustrative only — not a real capture. The full system-wide network monitor is a separate,
        backend-driven piece of this project.
      </p>
      <ul className="max-h-64 overflow-y-auto">
        {events.map((event) => (
          <li
            key={event.id}
            className="pop-enter border-b border-white/5 px-3.5 py-2 font-mono text-xs last:border-0"
          >
            <div className="flex items-center gap-2">
              <span className="text-ash/60">{event.time}</span>
              <span className="rounded bg-obsidian px-1.5 py-0.5 text-ash">{event.protocol}</span>
              <span className="text-bone">{event.destination}</span>
            </div>
            <p className="mt-0.5 truncate text-ash/70">{event.label}</p>
          </li>
        ))}
      </ul>
    </div>
  )
}

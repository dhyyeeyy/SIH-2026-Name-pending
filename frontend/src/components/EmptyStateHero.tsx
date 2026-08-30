import { ChatInput } from "./ChatInput"

interface EmptyStateHeroProps {
  onSubmit: (query: string, attachments: File[]) => void
  useRag: boolean
  onToggleRag: () => void
}

// CSS-only stand-in for the painterly poster artwork: a warm ember glow
// emanating from one point in an otherwise unlit room, over a faint
// blueprint grid (the engineering-drawing world this product actually
// lives in), with a grain overlay for the poster texture.
export function EmptyStateHero({ onSubmit, useRag, onToggleRag }: EmptyStateHeroProps) {
  return (
    <div className="blueprint-grid grain relative flex flex-1 flex-col items-center justify-center overflow-hidden px-6">
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            "radial-gradient(ellipse 60% 50% at 50% 65%, rgba(217,125,61,0.16) 0%, rgba(44,62,107,0.10) 45%, transparent 75%)",
        }}
        aria-hidden="true"
      />
      <div
        className="pointer-events-none absolute inset-0"
        style={{ background: "linear-gradient(180deg, rgba(20,18,15,0.4) 0%, rgba(20,18,15,0.85) 100%)" }}
        aria-hidden="true"
      />

      <div className="relative z-10 flex w-full max-w-2xl flex-col items-center gap-8 text-center">
        <div className="space-y-3">
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-ember">sovereign workbench</p>
          <h1 className="font-display text-[2rem] leading-tight font-normal italic text-bone sm:text-4xl md:text-5xl">
            What are we working on?
          </h1>
          <p className="mx-auto max-w-md text-sm text-ash">
            Everything here runs on this machine. Summarize a report, extract findings from a scan, or ask for a
            fix to your code.
          </p>
        </div>
        <div className="w-full">
          <ChatInput onSubmit={onSubmit} useRag={useRag} onToggleRag={onToggleRag} />
        </div>
      </div>
    </div>
  )
}

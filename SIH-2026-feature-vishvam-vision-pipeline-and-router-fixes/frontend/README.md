# Frontend — Sovereign Workbench

The web UI for PS26117. Built with React + Vite + Tailwind v4. Currently owned by Vishvam (reassigned from Sujal — see the team's `CLAUDE.md` for context on why).

This README is for anyone on the team who needs to run, understand, or extend the frontend — not just the original author.

---

## Quick start

**Prerequisites:** Node.js 20+ and npm (check with `node --version`).

```bash
cd frontend
npm install
npm run dev
```

Opens at `http://localhost:5173`. That's it — no backend, no Ollama, no Python environment needed to see the UI working. It runs against a **mock API** by default (see below), so you can develop/demo the frontend in total isolation from the rest of the stack.

Other scripts:
```bash
npm run build     # type-checks (tsc -b) then builds for production
npm run preview   # serves the production build locally
npm run lint       # oxlint
```

---

## The mock API — how the frontend works without a backend

Dharm's FastAPI backend doesn't exist yet (and even once it does, you may want to work on the UI without running the full Ollama + agent stack locally). So the frontend talks to a **mock client** that mirrors `agent/agent.py`'s real `run()` output shape exactly — same `AgentResult` structure, same trace step names, same timing feel (artificial delays so loading states are visible).

- `src/api/mockAgentClient.ts` — the mock implementation. Classifies queries by keyword to fake routing, returns realistic trace sequences.
- `src/api/realAgentClient.ts` — the real implementation, POSTs to `{VITE_API_BASE_URL}/api/agent/run` as `FormData`. **Not yet connected to anything real** — the endpoint shape here is a guess based on the agent's contract; confirm with Dharm once his backend exists and adjust if needed.
- `src/api/index.ts` — the single switch point. Everything in the app imports `runAgent` from here, never the mock/real clients directly.

**To switch to the real backend once it exists**, set in a `.env.local` file (gitignored):
```
VITE_USE_MOCK_API=false
VITE_API_BASE_URL=http://localhost:8000
```
No component code needs to change — that's the whole point of the switch point pattern.

**Manual test hooks in the mock** (type these as your query to exercise otherwise-hard-to-trigger states):
- `"simulate error"` → throws, to see the error UI
- `"no rag match"` (combined with any other text) → returns zero relevant RAG chunks, to see the "answered from general knowledge" tag
- Any query containing a code-ish keyword (`function`, `code`, `script`, `python`, `write a`, `bug`, `refactor`) → routes to the mock "code" response, which triggers the canvas panel

---

## Project structure

```
src/
├── App.tsx                 # top-level layout + canvas/session state wiring
├── main.tsx                 # React root, StrictMode
├── index.css                 # design tokens (@theme), global styles, animation keyframes
├── api/
│   ├── index.ts              # runAgent() switch point (mock vs real)
│   ├── mockAgentClient.ts    # mock backend, mirrors agent.run()'s contract
│   └── realAgentClient.ts    # real backend client (not yet connected)
├── components/                # all UI components, one per file
│   ├── Sidebar.tsx            # collapsible left nav — sessions, knowledge base
│   ├── TopBar.tsx             # title, sovereignty chip, canvas toggle
│   ├── SovereigntyChip.tsx    # "offline · 0 external calls" — the signature element
│   ├── EmptyStateHero.tsx      # empty-state screen (no active session)
│   ├── ConversationView.tsx    # active session: message list + docked input
│   ├── MessageBubble.tsx       # one chat message (user or assistant)
│   ├── ChatInput.tsx           # the composer: text, attach, RAG switch, send
│   ├── Switch.tsx              # reusable ON/OFF toggle
│   ├── Tooltip.tsx             # reusable CSS-only hover/focus tooltip
│   ├── TraceView.tsx           # collapsible step-by-step trace under a response
│   ├── CodeCanvas.tsx          # right-side panel showing extracted code
│   ├── CodeReferenceCard.tsx   # "Open in canvas" card shown in place of raw code
│   └── icons.tsx               # inline SVG icon set (no icon library dependency)
├── hooks/
│   └── useAgentChat.ts         # session state, RAG toggle state, submit() flow
├── lib/
│   ├── parseCodeBlocks.ts      # splits a response into text/code segments
│   └── messageUtils.ts         # trace-parsing helpers (e.g. extract model name)
└── types/
    ├── agent.ts                 # mirrors agent/agent.py's AgentResult contract
    ├── chat.ts                   # frontend-only chat/session types
    └── canvas.ts                  # canvas panel content type
```

---

## Design system

Defined as Tailwind v4 `@theme` tokens in `src/index.css` — "Obsidian Vault": a warm near-black base (`obsidian`), an ember accent used sparingly for state/emphasis, Fraunces for display headings, Inter for UI text, IBM Plex Mono for technical/trace content. If you're adding a component, reuse these tokens (`bg-obsidian`, `text-ember`, `font-display`, etc.) rather than introducing new colors — the palette is deliberately small.

Animations are curated, not blanket — message bubbles fade in once, the canvas panel slides in from the right, the mobile sidebar drawer slides in from the left. All respect `prefers-reduced-motion` via a global rule in `index.css`. Follow this pattern rather than adding animation library dependencies.

---

## Known gaps / what's not done yet

- **No real backend connection** — everything runs against the mock. See "The mock API" above for how to switch once Dharm's service exists.
- **No `files_to_generate` UI** — the `AgentResult` type supports it (for Word/PPT/Excel deliverables from `docgen.py`), but nothing in the UI renders it yet.
- **No auth/RBAC** — that's a separate piece of the system (see the team's `CLAUDE.md`), not built here.
- **Single active canvas** — only one code block can be "open" in the canvas at a time; opening a new one replaces the old. Fine for now, may need revisiting if a response regularly produces multiple distinct files.

---

## Questions?

The contract this frontend depends on (`AgentResult`, trace step names, the `run()` signature) is documented in the team's `CLAUDE.md` at the repo root, Section 7 — that's the source of truth if the mock and the real backend ever disagree.

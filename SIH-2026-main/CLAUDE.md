# PS 26117 — Sovereign On-Premise Agentic AI Workbench
## CLAUDE.md — AI/Agent Lead Scope (Vishvam)

This file is read automatically at the start of every Claude Code session in this repo. It gives full project context so any session — even one only touching `/router` or `/agent` — understands the whole system it's a part of. Read alongside `task_sheet.md` (the phased checklist for this specific role).

---

## 1. What This Project Is, and Why

This is our team's build for **Smart India Hackathon 2026, Problem Statement 26117**. The internal college round requires a PPT plus a working prototype covering roughly 40% of the full system.

**The problem, in plain terms:** organizations with confidential data (refineries, PSUs, defence manufacturing, government offices) can't use cloud AI assistants (Claude, Codex, ChatGPT) because their data — engineering drawings, financials, unreleased designs, internal correspondence — can't leave their premises. People either do this work manually or risk leaking data into public tools. Nothing deployable exists today that lets these organizations use an AI assistant the way others use Claude or Codex, entirely on their own hardware.

**What we're building:** a self-hosted, air-gapped AI workbench that:
1. Runs entirely on our own machine — **zero external network calls, ever, at any point**
2. Uses **multiple open-weight models**, not one — with **automatic routing** to the right model per task, and the ability to add new models later without redesigning anything
3. Acts as a genuine **agent** — multi-step planning, tool use, iteration — not a single-turn chatbot
4. Handles **multimodal input** — scanned PDFs, photos, engineering drawings — via local OCR/vision
5. Produces **real deliverable files** — Word/PPT/Excel documents, working code, calculations — not just chat replies
6. Grounds itself in **our own documents** (SOPs, manuals, correspondence) via local RAG, never external
7. Can **prove**, live, that nothing ever leaves the machine (network monitor visible during demo)

**This file's scope covers requirements 2, 3, 4, 5 (partially), and 6 above** — the AI/ML layer. Everything else (the web app, RBAC, file generation, network proof) is owned by teammates in other folders.

---

## 2. Your Scope in This Repo

You (this Claude Code session) own **`/router`, `/agent`, and, as of 2026-08-30, `/frontend`**. Sujal is unable to continue frontend work, so that scope has been reassigned to Vishvam for this build. Do not modify files in `/backend`, `/docs`, `/testing`, or `/pptx` — those still belong to other team members (Dharm, Aarav, Tanvi, Yash respectively). If a change seems to require touching one of those folders, stop and flag it rather than editing it directly — coordinate with the owner first.

**Files you own:**
- `/router/router.py`
- `/router/model_config.json`
- `/router/test_router.py`
- `/agent/agent.py`
- `/agent/rag.py`
- `/agent/test_agent.py`
- `/frontend/**` (build from scratch — did not exist before this reassignment)

---

## 3. Hardware Constraints (Non-Negotiable — Design Around These)

Confirmed hardware for the internal round:
- **Machine A:** 4GB dedicated VRAM + 6-7GB integrated (Ollama only accelerates on the dedicated 4GB — integrated graphics are not usable for GPU acceleration)
- **Machine B:** no dedicated GPU, 16GB system RAM (CPU-only inference)

This is why every model in the pool is sized at 3-4B parameters, not larger. The PS itself explicitly permits this: *"use a smaller open-weight model if 120B-class hardware isn't available at the venue."* Do not suggest or default to larger models assuming more powerful hardware — it does not exist for this project.

---

## 4. The Model Pool (Locked In — Do Not Substitute Without Discussion)

| Role | Model | Why |
|---|---|---|
| General reasoning / orchestration | `qwen3:1.7b` | Lighter footprint for Machine A/B constraints; team-finalized swap from `qwen3:4b` |
| Coding specialist | `qwen2.5-coder:3b` | Purpose-built for code generation/repair; ~1.9GB |
| Vision / OCR specialist | `qwen3.5:2b` | Team-finalized swap from `qwen2.5-vl:3b` — **verify exact Ollama tag exists before pulling; unconfirmed as of this update** |
| Local embeddings (RAG + router) | `nomic-embed-text` | Runs via Ollama, fully local, <500MB, **must be pinned to CPU** |

**Note:** This table was updated 2026-08-28 per team decision. The original locked pool (`qwen3:4b` / `qwen2.5-vl:3b`) is documented in git history if a rollback is needed. `qwen3.5:2b` is confirmed as a real, pullable Ollama tag (verified via `ollama show qwen3.5:2b` — architecture `qwen35`, 2.3B params, capabilities: completion/vision/tools/thinking) and has been tested end-to-end for vision extraction against real document images with accurate results.

**`qwen3-vl:4b-instruct` / `qwen3-vl:4b-thinking` evaluation: SKIPPED per team decision (2026-08-28).** The pool above (`qwen3:1.7b` general, `qwen3.5:2b` vision) is final for this round — not a fallback pending evaluation. If this decision is revisited, update this section and re-run the VRAM/tool-calling checks described previously before switching.

**⚠️ Known discrepancy:** `PS26117_TaskSheet_Vishvam.pdf` (the official phased checklist) still lists the original pool (`qwen3:4b` / `qwen2.5-vl:3b` / `qwen2.5-coder:3b`) as canonical and includes the `qwen3-vl` evaluation as a required Phase 1 checklist item. That PDF has not been updated to reflect this swap — flag this to whoever owns/maintains the task sheet so the two documents don't disagree at review time.

All models pulled via:
```
ollama pull qwen3:1.7b
ollama pull qwen2.5-coder:3b
ollama pull qwen3.5:2b
ollama pull nomic-embed-text
```

---

## 5. Full System Architecture (Context — Most of This Is Outside Your Scope)

```
                [User via Web Dashboard — login + role check]      <- Sujal (frontend) + Dharm (backend)
                                |
                                v
              [Semantic Router — embedding lookup (CPU-pinned      <- YOUR SCOPE: /router
               model, 0% GPU) against labelled examples per
               category, milliseconds. Override: no text layer /
               image attached -> Vision. Otherwise -> General
               or Code directly, no vision step at all.]
                    |                |                  |
                    v                v                  v
          [qwen3:4b            [qwen2.5-coder:3b   [qwen2.5-vl:3b        <- YOUR SCOPE: /agent
           General reasoning    Code generation +     Vision/OCR — runs
           + RAG + planning,    JSON-constrained,      ONCE per new scanned
           JSON-constrained]    pre-warmed sandbox     doc as ingestion,
                    ^            via docker exec]       outputs structured
                    |                |                JSON + stores FULL
                    |                v                raw OCR text too
                    |          [Warm Docker Sandbox          |          <- Dharm's scope
                    |           — no network,                v
                    |           reused, not recreated] [Embedded + written
                    |                                   into vector store —
                    +---------------------------------  summary AND raw text,
                                                          never re-run per Q]
                                |
                                v
          [Local Vector DB (Chroma/FAISS, via CPU-pinned              <- YOUR SCOPE: /agent/rag.py
           nomic-embed/bge-small) — SOPs, manuals,
           correspondence, vision summaries + raw text]
                                |
                                v
          [Output Generators: python-docx / python-pptx / openpyxl]    <- Dharm's scope

    ══════════════════════════════════════════════════════════════
     CROSS-CUTTING: Audit Log — every component writes here             <- Dharm's scope
     synchronously, the instant a decision/call happens, flushed
     to disk immediately. Survives a mid-task crash.
    ══════════════════════════════════════════════════════════════
                                |
                                v
          [Live Network Monitor — visible proof of zero              <- Yash's scope
           external calls throughout]
```

**Your job is everything from the router down to the vector database.** Dharm's FastAPI service calls into your code; you don't need to build or touch the API layer, the sandbox container itself, the document-generation libraries, or the frontend.

---

## 6. Design Decisions Already Locked In (Don't Relitigate These Without Reason)

- **Router is semantic/embedding-based, not LLM-based.** It reuses the RAG embedding model (`nomic-embed-text`) rather than asking a full model to classify each request — this costs no separate VRAM and runs in milliseconds. Hard override: no extractable text layer or an image attached → always route to vision.
- **Vision runs once per document, not once per query.** A new scanned document is read by the vision model exactly once. Its output — both a structured summary (`{"document_type":..., "key_findings":[...], "recommended_action":...}`) AND the full raw OCR text — is embedded and stored in the same vector store as regular documents. Every subsequent question about that document goes through the normal text-only RAG path with **no repeat vision call and no model swap**.
- **The embedding model is pinned to CPU**, always — it must never compete with the actively-generating model for the 4GB VRAM budget.
- **Tool-call output is constrained to valid JSON**, and the agent loop has a **hard recursion/retry cap** (LangGraph's `recursion_limit`, something like 15) — small models are more prone to malformed tool calls than larger ones, and an uncapped retry loop is the single most likely way this system visibly breaks in a live demo.
- **The model registry (`model_config.json`) is the extensibility mechanism.** Adding a new model later means adding an entry to this file, not changing router or agent code. This directly satisfies the PS's requirement that new open-weight models be addable without redesigning the system.

---

## 7. The Interface Dharm's Backend Depends On

Expose your agent as a function Dharm can call directly from `app.py`:
```python
def run(
    query: str,
    user_id: str,
    attachments: list[str] | None = None,
    use_rag: bool = True,
) -> AgentResult:
    """
    Returns an AgentResult containing:
    - final_answer: str
    - trace: list[dict]  # one entry per step, e.g. {"step": "router_decision", "detail": "..."}
    - files_to_generate: list[dict] | None  # structured content for docgen.py to turn into .docx/.pptx/.xlsx
    """
```
Treat this signature as a contract — if it needs to change, flag it to Dharm before changing it, since his code calls into it directly.

**Changelog (2026-08-30): added `use_rag: bool = True`.** Frontend exposes this as a user-facing toggle ("search my documents"). When `False`, the graph skips `retrieve_node` entirely for general/code queries (vision extraction is unaffected -- reading an attached image is a different operation from searching *other* stored documents). Trace logs `{"step": "rag_skipped", "detail": "disabled by user"}` when this happens, so the decision is visible rather than silent. Default `True` preserves prior behavior, so this is backward-compatible for any caller not yet passing it. Also: `rag.py`'s `retrieve()` now filters out chunks beyond `RELEVANCE_THRESHOLD` (cosine distance 0.6) rather than always returning the top-k regardless of relevance -- a query unrelated to anything ingested now surfaces as `{"step": "rag_retrieval", "detail": "0 relevant chunks found"}` and the model answers from its own knowledge, instead of being silently fed the "least-bad" irrelevant chunks as if they were real context.

---

## 8. What the Demo Must Prove (Why Any of This Matters)

The PS requires the prototype to demonstrate, even at reduced/internal-round scale:
1. **Model auto-selection across ≥2 task types** — e.g. a document-summary request routes to `qwen3:4b`, a coding request routes to `qwen2.5-coder:3b`, visibly logged
2. **An agentic task end-to-end** — scanned inspection report → key findings extracted → a real Word file drafted
3. **A coding task run and verified in a sandbox**
4. **A multimodal task** — an image or scanned document genuinely understood
5. **Proof of zero external network calls** throughout all of the above

Your router and agent are directly responsible for proving #1, #2 (the reasoning/extraction part), and #4. Keep this in mind when deciding what "good enough for the internal round" means — these four are non-negotiable even at prototype scale, not full-scale polish.

---

## 9. Hard Rules

- **Never call an external API of any kind** — no cloud LLM APIs, no cloud embedding APIs, no telemetry, nothing that leaves the machine. This is the single most important constraint in the entire project; the whole PS is built around this claim being true and provable.
- **Never assume larger hardware than Section 3 specifies.**
- **Don't touch other team members' folders.**
- **Every new piece of logic gets a test** — this repo's convention is a `test_*.py` file alongside the code it tests, using `pytest`.

---

## 10. Commands

```bash
# Run the router's test suite
pytest router/test_router.py -v

# Run the agent's test suite
pytest agent/test_agent.py -v

# Check what's currently loaded in Ollama and whether it's on GPU or CPU
ollama ps

# Benchmark a model's tokens/sec
ollama run <model> --verbose
```

---

## 11. GitHub Conventions (Shared Across the Whole Team)

- Branch naming: `feature/vishvam-<short-description>`
- Commit prefix: `[router]` or `[agent]`
- Never push directly to `main` — open a Pull Request, get one teammate's review, then merge
- Push small, working pieces often rather than large batches

---

## 12. Where to Look for More Detail

- `task_sheet.md` (supplied alongside this file) — the phased checklist for this role
- `/docs/PS_CHECK.md` (Aarav's file) — verbatim official PS text cross-checked against our interpretation; check this if anything here seems ambiguous
- `/docs/BUILT_VS_PLANNED.md` — what's actually working vs. roadmap, kept current as the build progresses

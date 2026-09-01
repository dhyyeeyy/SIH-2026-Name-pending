"""
Agent entry point, built as a LangGraph state machine: plan -> act ->
check result -> decide next step, rather than a single-pass pipeline.
Dharm's backend calls run() directly -- treat its signature as a
contract; flag before changing it.

Graph shape:
    plan -> (vision_extract | retrieve | generate) -> generate -> END
    use_rag=False (or role == vision) skips retrieve entirely -- plan
    routes straight to generate. RAG retrieval also drops chunks beyond
    RELEVANCE_THRESHOLD (see rag.py), so a query unrelated to anything
    ingested still gets a normal answer from the model's own knowledge
    rather than being polluted with the "closest but irrelevant" chunks.
    vision_extract loops back to itself on malformed JSON, up to
    MAX_STEP_RETRIES times, then falls through to a graceful "fail" node
    instead of crashing -- small models are more prone to malformed
    tool-call JSON than large ones, and an uncapped retry loop is the
    single most likely way this system visibly breaks in a live demo.
    generate loops back to itself once if the model returns an empty
    response. RECURSION_LIMIT is an outer hard cap on total graph steps
    (LangGraph's recursion_limit), independent of the per-node retry
    counters, as a second line of defense against an infinite loop.
"""

import json
import os
import tempfile
from pathlib import Path
from typing import TypedDict

import ollama
from langgraph.graph import END, StateGraph
from PIL import Image

import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "router"))
from router import route  # noqa: E402
from rag import ingest, retrieve  # noqa: E402

CONFIG_PATH = Path(__file__).parent.parent / "router" / "model_config.json"
RECURSION_LIMIT = 15
MAX_STEP_RETRIES = 3

# Ollama defaults to a 4096-token runtime context regardless of what a
# model architecturally supports -- an image alone can exceed that, so
# every chat call must request a larger window explicitly. Kept modest
# (not the model's full context_window from model_config.json) to stay
# within Machine A's 4GB VRAM budget -- KV cache scales with this.
RUNTIME_CONTEXT = 8192

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif"}

# Vision token cost scales with image resolution -- an uncapped phone
# photo can blow past RUNTIME_CONTEXT on its own and take minutes on
# CPU. Downscale before sending; this is plenty for OCR-quality text.
MAX_IMAGE_DIMENSION = 1280


def _downscale_for_vision(image_path: str) -> str:
    """
    Resize an image so its longest side is at most MAX_IMAGE_DIMENSION,
    preserving aspect ratio. Returns a path to the (possibly new,
    temp-file) resized image; returns the original path unchanged if
    it's already small enough.
    """
    with Image.open(image_path) as img:
        width, height = img.size
        if max(width, height) <= MAX_IMAGE_DIMENSION:
            return image_path

        scale = MAX_IMAGE_DIMENSION / max(width, height)
        new_size = (int(width * scale), int(height * scale))
        resized = img.convert("RGB").resize(new_size, Image.LANCZOS)

        fd, temp_path = tempfile.mkstemp(suffix=".jpg")
        os.close(fd)
        resized.save(temp_path, "JPEG", quality=90)
        return temp_path


def _has_extractable_text(attachments: list[str] | None) -> bool:
    """
    Cheap heuristic: image files have no text layer, so they always need
    vision. Anything else (e.g. a .txt/.pdf with a real text layer) is
    assumed to have extractable text. PDF text-layer detection is out of
    scope for this stub -- extend here if scanned PDFs need it later.
    """
    if not attachments:
        return True
    return Path(attachments[0]).suffix.lower() not in IMAGE_EXTENSIONS


class AgentResult(TypedDict):
    final_answer: str
    trace: list[dict]
    files_to_generate: list[dict] | None


class AgentState(TypedDict, total=False):
    query: str
    user_id: str
    attachments: list[str] | None
    use_rag: bool
    trace: list[dict]
    role: str
    context: str
    vision_summary: dict | None
    vision_retries: int
    generate_retries: int
    final_answer: str


def _load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _model_for_role(role: str) -> str:
    config = _load_config()
    return config["models"][role]["ollama_tag"]


def _call_vision_model(attachment_path: str, trace: list[dict]) -> dict:
    """
    One vision-model call. Raises json.JSONDecodeError if the model's
    output isn't valid JSON -- the caller (vision_extract_node) is
    responsible for catching that and deciding whether to retry.
    """
    vision_model = _model_for_role("vision")
    resized_path = _downscale_for_vision(attachment_path)
    if resized_path != attachment_path:
        trace.append({"step": "image_downscaled", "detail": f"resized to max {MAX_IMAGE_DIMENSION}px"})

    try:
        response = ollama.chat(
            model=vision_model,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Extract this document's content. Respond with JSON: "
                        '{"document_type": str, "key_findings": [str], '
                        '"recommended_action": str, "raw_text": str}'
                    ),
                    "images": [resized_path],
                }
            ],
            format="json",
            options={"num_ctx": RUNTIME_CONTEXT},
        )
    finally:
        if resized_path != attachment_path:
            os.remove(resized_path)

    trace.append({"step": "vision_extraction", "detail": f"model={vision_model}"})
    return json.loads(response["message"]["content"])  # may raise json.JSONDecodeError


def plan_node(state: AgentState) -> AgentState:
    routing = route(
        state["query"],
        attachments=state.get("attachments"),
        has_extractable_text=_has_extractable_text(state.get("attachments")),
    )
    state["trace"].append({"step": "router_decision", "detail": routing})
    state["role"] = routing["role"]

    if routing["role"] != "vision" and not state.get("use_rag", True):
        state["trace"].append({"step": "rag_skipped", "detail": "disabled by user"})

    return state


def vision_extract_node(state: AgentState) -> AgentState:
    attempt = state.get("vision_retries", 0)
    attachment_path = state["attachments"][0]

    try:
        extracted = _call_vision_model(attachment_path, state["trace"])
    except json.JSONDecodeError as e:
        state["vision_retries"] = attempt + 1
        state["trace"].append(
            {"step": "vision_extraction_failed", "detail": f"attempt {attempt + 1}: malformed JSON ({e})"}
        )
        return state

    summary = {
        "document_type": extracted.get("document_type"),
        "key_findings": extracted.get("key_findings"),
        "recommended_action": extracted.get("recommended_action"),
    }
    raw_text = extracted.get("raw_text", "")

    ingest(json.dumps(summary), {"content_type": "summary", "source": attachment_path})
    ingest(raw_text, {"content_type": "raw_ocr", "source": attachment_path})
    state["trace"].append({"step": "rag_ingest", "detail": f"stored summary + raw_ocr for {attachment_path}"})

    state["vision_summary"] = summary
    state["context"] = json.dumps(summary)
    return state


def route_after_vision(state: AgentState) -> str:
    if state.get("vision_summary"):
        return "generate"
    if state.get("vision_retries", 0) >= MAX_STEP_RETRIES:
        return "fail"
    return "vision_extract"


def retrieve_node(state: AgentState) -> AgentState:
    hits = retrieve(state["query"], k=5)
    detail = f"{len(hits)} chunks retrieved" if hits else "0 relevant chunks found"
    state["trace"].append({"step": "rag_retrieval", "detail": detail})
    state["context"] = "\n\n".join(h["text"] for h in hits)
    return state


def generate_node(state: AgentState) -> AgentState:
    role = state["role"]
    model_role = "general" if role == "vision" else role
    model = _model_for_role(model_role)
    context = state.get("context", "")

    response = ollama.chat(
        model=model,
        messages=[
            {"role": "system", "content": f"Relevant context:\n{context}" if context else ""},
            {"role": "user", "content": state["query"]},
        ],
        options={"num_ctx": RUNTIME_CONTEXT},
    )
    state["final_answer"] = response["message"]["content"]
    state["trace"].append({"step": "model_response", "detail": f"model={model}"})
    return state


def route_after_generate(state: AgentState) -> str:
    if state.get("final_answer", "").strip():
        return "end"
    attempt = state.get("generate_retries", 0)
    if attempt >= MAX_STEP_RETRIES:
        return "fail"
    state["generate_retries"] = attempt + 1
    return "generate"


def fail_node(state: AgentState) -> AgentState:
    state["final_answer"] = (
        "I wasn't able to complete this request reliably after multiple attempts. "
        "Please try rephrasing, or try again."
    )
    state["trace"].append({"step": "failed", "detail": "exceeded retry budget"})
    return state


def _route_after_plan(state: AgentState) -> str:
    if state["role"] == "vision" and state.get("attachments"):
        return "vision_extract"
    if not state.get("use_rag", True):
        return "generate"
    return "retrieve"


def _build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("plan", plan_node)
    graph.add_node("vision_extract", vision_extract_node)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("generate", generate_node)
    graph.add_node("fail", fail_node)

    graph.set_entry_point("plan")
    graph.add_conditional_edges(
        "plan",
        _route_after_plan,
        {"vision_extract": "vision_extract", "retrieve": "retrieve", "generate": "generate"},
    )
    graph.add_conditional_edges(
        "vision_extract", route_after_vision, {"generate": "generate", "vision_extract": "vision_extract", "fail": "fail"}
    )
    graph.add_edge("retrieve", "generate")
    graph.add_conditional_edges(
        "generate", route_after_generate, {"end": END, "generate": "generate", "fail": "fail"}
    )
    graph.add_edge("fail", END)

    return graph.compile()


_compiled_graph = _build_graph()


def run(
    query: str,
    user_id: str,
    attachments: list[str] | None = None,
    use_rag: bool = True,
) -> AgentResult:
    initial_state: AgentState = {
        "query": query,
        "user_id": user_id,
        "attachments": attachments,
        "use_rag": use_rag,
        "trace": [],
    }

    final_state = _compiled_graph.invoke(initial_state, config={"recursion_limit": RECURSION_LIMIT})

    return AgentResult(
        final_answer=final_state.get("final_answer", ""),
        trace=final_state["trace"],
        files_to_generate=None,
    )

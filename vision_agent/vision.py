import asyncio
from pathlib import Path
import sys
sys.path.append("C:/Users/Dharm/Desktop/Sovereign_AI")
from vision_agent import analyze_document
from vision_kb_lookup import find_prior_findings_with_source
from knowledge.ingest import ingest_vision_result


def run_vision_task(
    file_path: str,
    question: str,
    context: dict,
    cross_reference: bool = False,
    cross_reference_query: str | None = None,
    store_result: bool = True,
    source_id: str | None = None,
) -> dict:
    """
    file_path: an image (.png/.jpg/.jpeg/.bmp/.tiff/.webp) or a PDF.
        File type is detected automatically inside analyze_document() —
        the caller doesn't need to branch on extension.

    context: passed straight through to analyze_document (matches coder.py's
        context-dict pattern; currently unused by vision_agent itself but
        kept for consistency/future use, e.g. output_dir).

    cross_reference: if True, also looks up prior OBSERVED findings related
        to this file (e.g. same equipment tag) from the knowledge base.
        Uses cross_reference_query if given, else falls back to `question`.

    store_result: defaults to True — every vision analysis is ingested into
        the knowledge base so it builds institutional memory (past
        inspections, prior tag states) automatically. Pass False explicitly
        for ephemeral calls (UI preview, retry, test run) that should NOT
        be written to the KB. source_id defaults to the file's stem if
        not given.
    """
    result = asyncio.run(analyze_document(file_path, question, context))

    output = {
        "observed": result["observed"],
        "unclear": result["unclear"],
        "raw": result["raw"],
        "prior_findings": [],
        "chunks_stored": 0,
    }

    if cross_reference:
        query = cross_reference_query or question
        output["prior_findings"] = find_prior_findings_with_source(query)

    if store_result:
        sid = source_id or Path(file_path).stem
        output["chunks_stored"] = ingest_vision_result(result, source_id=sid, image_path=file_path)

    return output
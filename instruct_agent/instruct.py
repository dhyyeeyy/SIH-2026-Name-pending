import asyncio
import logging
from typing import Optional
from instruct_agent import InstructAgentError, run_instruct_task
logger = logging.getLogger(__name__)


def run_instruct(
    instruction: str,
    query: Optional[str] = None,
    source_id: Optional[str] = None,
    content_types: Optional[list[str]] = None,
    n_results: int = 5,
) -> dict:
    
    try:
        result = asyncio.run(
            run_instruct_task(
                instruction=instruction,
                query=query,
                source_id=source_id,
                content_types=content_types,
                n_results=n_results,
            )
        )
        result["instruction"] = instruction
        result["error"] = False
        return result

    except InstructAgentError as e:
        logger.error("instruct.py: instruct agent failed: %s", e)
        return {
            "answer": f"Could not complete this request: {e}",
            "insufficient_context": False,
            "sources_used": [],
            "n_sources_retrieved": 0,
            "instruction": instruction,
            "error": True,
        }
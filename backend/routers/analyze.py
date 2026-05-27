"""
POST /analyze — run the Universal Review Agent over previously uploaded files.

Body:
    {
      "file_ids": ["abc1234_main.py", ...],
      "model_id": "qwen2.5-coder:1.5b",     // optional, falls back to ACTIVE_MODEL_ID
      "chunking_strategy": "function",      // optional, falls back to ACTIVE_CHUNKING_STRATEGY
      "skill": "static_review"              // optional, falls back to DEFAULT_SKILL
    }
"""

import logging
import time

from fastapi import APIRouter, HTTPException

from agents.ingestion_agent import IngestionAgent
from agents.universal_review_agent import UniversalReviewAgent
from config import (
    ACTIVE_CHUNKING_STRATEGY,
    ACTIVE_MODEL_ID,
    DEFAULT_SKILL,
    UPLOAD_DIR,
)
from models.schemas import AnalyzeRequest

router = APIRouter()
logger = logging.getLogger("ura.analyze")


@router.post("/analyze")
def analyze(request: AnalyzeRequest) -> dict:
    if not request.file_ids:
        raise HTTPException(status_code=400, detail="file_ids is required")

    model_id = (request.model_id or ACTIVE_MODEL_ID).strip()
    chunking_strategy = request.chunking_strategy or ACTIVE_CHUNKING_STRATEGY
    skill_name = request.skill or DEFAULT_SKILL

    logger.info(
        "Analyze request: %d file(s) | model=%s | strategy=%s | skill=%s",
        len(request.file_ids),
        model_id,
        chunking_strategy,
        skill_name,
    )

    try:
        agent = UniversalReviewAgent(skill_name=skill_name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    ingestion = IngestionAgent()
    results = []
    overall_start = time.perf_counter()

    for file_idx, file_id in enumerate(request.file_ids, start=1):
        path = UPLOAD_DIR / file_id
        if not path.exists():
            raise HTTPException(status_code=404, detail=f"File not found: {file_id}")

        file_name, language, chunks = ingestion.ingest(path, chunking_strategy)
        logger.info(
            "[%d/%d] %s | %s | %d chunks via %s",
            file_idx,
            len(request.file_ids),
            file_name,
            language,
            len(chunks),
            chunking_strategy,
        )

        for chunk_idx, chunk in enumerate(chunks, start=1):
            logger.info(
                "  chunk %d/%d: %s (lines %d-%d)",
                chunk_idx,
                len(chunks),
                chunk.chunk_id,
                chunk.start_line,
                chunk.end_line,
            )
            review = agent.review_chunk(
                chunk=chunk,
                model_id=model_id,
                file_name=file_name,
                chunking_strategy=chunking_strategy,
            )
            results.append(review)

    elapsed = time.perf_counter() - overall_start
    logger.info(
        "Done: %d chunks reviewed across %d file(s) in %.1fs",
        len(results),
        len(request.file_ids),
        elapsed,
    )

    # Aggregate scoring across all chunks (per-skill scorer; no-op if the
    # skill doesn't ship a scoring.py).
    scoring = agent.compute_scoring(results)

    return {
        "model": model_id,
        "chunking_strategy": chunking_strategy,
        "skill": skill_name,
        "results": results,
        "scoring": scoring,
    }

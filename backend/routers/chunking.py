"""
GET /chunking-strategies — list registered chunking strategies and the active one.
"""

from fastapi import APIRouter

from config import ACTIVE_CHUNKING_STRATEGY, SUPPORTED_CHUNKING_STRATEGIES

router = APIRouter()


@router.get("/chunking-strategies")
def chunking_strategies() -> dict:
    return {
        "active": ACTIVE_CHUNKING_STRATEGY,
        "strategies": SUPPORTED_CHUNKING_STRATEGIES,
    }

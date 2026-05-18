"""
GET /ollama/health — quick diagnostic for the Run button.

The frontend uses this to decide whether to show:
- "Ollama is not running" banner
- "Active model is not pulled" banner

If Ollama is down, the agent still runs deterministic checks and returns
results — but the UI should warn the user that SLM reasoning is missing.
"""

from fastapi import APIRouter

from config import ACTIVE_MODEL_ID
from llm.ollama_client import (
    is_model_installed,
    is_ollama_reachable,
    list_installed_models,
)

router = APIRouter()


@router.get("/ollama/health")
def ollama_health() -> dict:
    reachable = is_ollama_reachable()
    installed = list_installed_models() if reachable else []
    return {
        "reachable": reachable,
        "installed_models": installed,
        "active_model": ACTIVE_MODEL_ID,
        "active_model_pulled": is_model_installed(ACTIVE_MODEL_ID, installed),
        "hint": (
            None
            if reachable
            else "Start Ollama with `ollama serve` in another terminal."
        ),
    }

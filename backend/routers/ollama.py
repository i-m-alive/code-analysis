"""
GET /ollama/health — quick diagnostic for the Run button.

The frontend uses this to decide whether to show:
- "Ollama is not running" banner
- "Active model is not pulled" banner

If Ollama is down, the agent still runs deterministic checks and returns
results — but the UI should warn the user that SLM reasoning is missing.
"""

from fastapi import APIRouter

from config import ACTIVE_MODEL_ID, BEDROCK_MODEL_ID
from llm.bedrock_client import is_bedrock_available
from llm.ollama_client import (
    is_model_installed,
    is_ollama_reachable,
    list_installed_models,
)

router = APIRouter()


@router.get("/ollama/health")
def ollama_health() -> dict:
    is_bedrock = ACTIVE_MODEL_ID == BEDROCK_MODEL_ID
    reachable = is_ollama_reachable()
    installed = list_installed_models() if reachable else []

    if is_bedrock:
        return {
            "reachable": reachable,
            "installed_models": installed,
            "active_model": ACTIVE_MODEL_ID,
            "active_model_provider": "bedrock",
            "active_model_pulled": is_bedrock_available(),
            "hint": None,
        }

    return {
        "reachable": reachable,
        "installed_models": installed,
        "active_model": ACTIVE_MODEL_ID,
        "active_model_provider": "ollama",
        "active_model_pulled": is_model_installed(ACTIVE_MODEL_ID, installed),
        "hint": (
            None
            if reachable
            else "Start Ollama with `ollama serve` in another terminal."
        ),
    }

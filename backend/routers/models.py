"""
GET /models — list supported models.

AWS Bedrock model is always included (when credentials are present).
Ollama models are only included when the local Ollama server is reachable.
"""

from fastapi import APIRouter

from config import ACTIVE_MODEL_ID, SUPPORTED_MODELS
from llm.bedrock_client import is_bedrock_available
from llm.ollama_client import is_model_installed, is_ollama_reachable, list_installed_models

router = APIRouter()


@router.get("/models")
def models() -> dict:
    ollama_online = is_ollama_reachable()
    installed_ollama = list_installed_models() if ollama_online else []

    out = []
    for entry in SUPPORTED_MODELS:
        provider = entry.get("provider", "ollama")
        if provider == "bedrock":
            out.append({**entry, "installed": is_bedrock_available()})
        elif ollama_online:
            out.append({
                **entry,
                "installed": is_model_installed(entry["id"], installed_ollama),
            })

    return {
        "active": ACTIVE_MODEL_ID,
        "models": out,
        "installed_locally": sorted(installed_ollama),
    }

"""
GET /models — list supported SLMs and report which are actually installed
in the local Ollama runtime.
"""

from fastapi import APIRouter

from config import ACTIVE_MODEL_ID, SUPPORTED_MODELS
from llm.ollama_client import is_model_installed, list_installed_models

router = APIRouter()


@router.get("/models")
def models() -> dict:
    installed = list_installed_models()
    out = []
    for entry in SUPPORTED_MODELS:
        out.append({
            **entry,
            "installed": is_model_installed(entry["id"], installed),
        })
    return {
        "active": ACTIVE_MODEL_ID,
        "models": out,
        "installed_locally": sorted(installed),
    }

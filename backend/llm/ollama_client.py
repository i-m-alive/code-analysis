"""
Thin synchronous client for the local Ollama runtime.

We deliberately avoid the official `ollama` Python SDK so we don't pin to any
particular wire format change. We only use the documented `/api/generate` and
`/api/tags` endpoints.
"""

import json
from typing import List

import httpx

from config import (
    OLLAMA_GENERATE_ENDPOINT,
    OLLAMA_TAGS_ENDPOINT,
    OLLAMA_TIMEOUT_SECONDS,
)


class OllamaError(RuntimeError):
    """Raised when the local Ollama runtime is unreachable or errors out."""


def list_installed_models() -> List[str]:
    """Return the names of locally-pulled Ollama models."""
    try:
        with httpx.Client(timeout=3) as client:
            response = client.get(OLLAMA_TAGS_ENDPOINT)
            response.raise_for_status()
            data = response.json()
            return [m.get("name", "") for m in data.get("models", [])]
    except Exception:
        # Ollama not running is a soft failure — the UI should still load.
        return []


def is_ollama_reachable() -> bool:
    """Quick health-probe used by the /ollama/health endpoint."""
    try:
        with httpx.Client(timeout=2) as client:
            response = client.get(OLLAMA_TAGS_ENDPOINT)
            return response.status_code == 200
    except Exception:
        return False


def is_model_installed(model_id: str, installed: List[str]) -> bool:
    """
    Lenient check: any pulled tag of the same family counts as installed.

    Example: config asks for `qwen2.5-coder:1.5b` but the user pulled
    `qwen2.5-coder:latest` — we still treat the family as available so the
    UI doesn't show a false "not pulled" warning.
    """
    if model_id in installed:
        return True
    family = model_id.split(":")[0]
    return any(name.split(":")[0] == family for name in installed)


def generate(model_id: str, prompt: str, system: str | None = None) -> str:
    """
    Run a single non-streaming completion against the local Ollama runtime.

    Returns the raw text from the model. Caller is responsible for parsing.
    """
    payload = {
        "model": model_id,
        "prompt": prompt,
        "stream": False,
        "options": {
            # Keep it deterministic-ish for benchmarking.
            "temperature": 0.2,
            "top_p": 0.9,
        },
    }
    if system:
        payload["system"] = system

    try:
        with httpx.Client(timeout=OLLAMA_TIMEOUT_SECONDS) as client:
            response = client.post(OLLAMA_GENERATE_ENDPOINT, json=payload)
            response.raise_for_status()
            data = response.json()
            return data.get("response", "")
    except httpx.HTTPError as exc:
        raise OllamaError(f"Ollama request failed: {exc}") from exc


def safe_json_extract(text: str) -> dict | list | None:
    """
    SLM outputs are messy: they often wrap JSON in prose or markdown fences.
    This helper extracts the first valid JSON object/array we can find.
    """
    if not text:
        return None

    # Strip common markdown fences.
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        # Remove a leading language hint like "json\n"
        if "\n" in cleaned:
            first_line, rest = cleaned.split("\n", 1)
            if first_line.lower().strip() in {"json", "javascript", ""}:
                cleaned = rest

    # Quick path.
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Find balanced braces/brackets.
    for opener, closer in (("{", "}"), ("[", "]")):
        start = cleaned.find(opener)
        end = cleaned.rfind(closer)
        if start != -1 and end != -1 and end > start:
            candidate = cleaned[start : end + 1]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue
    return None

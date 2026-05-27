"""
LangChain chat-model adapter for the review graph.

This keeps provider selection in one place while the LangGraph workflow can
call a single generate() function for both Ollama and AWS Bedrock.
"""

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from config import AWS_REGION, OLLAMA_HOST, OLLAMA_TIMEOUT_SECONDS


class LangChainLLMError(RuntimeError):
    """Raised when a LangChain-backed model call fails."""


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
            else:
                parts.append(json.dumps(block))
        return "\n".join(parts)
    return str(content or "")


def _build_model(model_id: str, provider: str):
    model_id = model_id.strip()
    try:
        if provider == "bedrock":
            from langchain_aws import ChatBedrockConverse

            return ChatBedrockConverse(
                model_id=model_id,
                region_name=AWS_REGION,
                temperature=0.2,
                top_p=0.9,
            )

        from langchain_ollama import ChatOllama

        try:
            return ChatOllama(
                model=model_id,
                base_url=OLLAMA_HOST,
                temperature=0.2,
                top_p=0.9,
                timeout=OLLAMA_TIMEOUT_SECONDS,
            )
        except TypeError:
            return ChatOllama(
                model=model_id,
                base_url=OLLAMA_HOST,
                temperature=0.2,
                top_p=0.9,
            )
    except ImportError as exc:
        raise LangChainLLMError(
            "LangChain integration packages are missing. "
            "Run `pip install -r requirements.txt` in backend/."
        ) from exc


def generate(model_id: str, prompt: str, provider: str, system: str | None = None) -> str:
    """Run a non-streaming chat completion through LangChain."""
    messages = []
    if system:
        messages.append(SystemMessage(content=system))
    messages.append(HumanMessage(content=prompt))

    try:
        response = _build_model(model_id, provider).invoke(messages)
        return _content_to_text(getattr(response, "content", response))
    except LangChainLLMError:
        raise
    except Exception as exc:
        raise LangChainLLMError(f"LangChain {provider} request failed: {exc}") from exc

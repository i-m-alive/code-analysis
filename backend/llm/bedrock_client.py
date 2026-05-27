"""
Thin synchronous client for AWS Bedrock using the Converse API.

Mirrors the interface of ollama_client.generate() so the agent can call
either backend without modification. The Converse API is model-agnostic —
the same request shape works for Claude, Titan, Llama, Mistral, etc.

Credentials are read from environment variables:
  AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION (default: us-east-1)
"""

import os

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from config import AWS_REGION, BEDROCK_MODEL_ID


class BedrockError(RuntimeError):
    """Raised when the AWS Bedrock call fails."""


def is_bedrock_available() -> bool:
    """Return True if Bedrock has the minimum local configuration present."""
    return bool(
        os.environ.get("AWS_ACCESS_KEY_ID")
        and os.environ.get("AWS_SECRET_ACCESS_KEY")
        and BEDROCK_MODEL_ID
        and BEDROCK_MODEL_ID != "REPLACE_WITH_YOUR_BEDROCK_MODEL_ID"
    )


def _get_client():
    return boto3.client(
        "bedrock-runtime",
        region_name=AWS_REGION,
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
        aws_session_token=os.environ.get("AWS_SESSION_TOKEN"),  # Optional
    )


def generate(model_id: str, prompt: str, system: str | None = None) -> str:
    """
    Run a single completion against AWS Bedrock via the Converse API.

    Returns the raw text from the model. Caller is responsible for parsing.
    """
    model_id = model_id.strip()
    messages = [{"role": "user", "content": [{"text": prompt}]}]
    kwargs = {
        "modelId": model_id,
        "messages": messages,
        "inferenceConfig": {
            "temperature": 0.2,
            "topP": 0.9,
        },
    }
    if system:
        kwargs["system"] = [{"text": system}]

    try:
        client = _get_client()
        response = client.converse(**kwargs)
        return response["output"]["message"]["content"][0]["text"]
    except (BotoCoreError, ClientError) as exc:
        raise BedrockError(f"Bedrock request failed: {exc}") from exc

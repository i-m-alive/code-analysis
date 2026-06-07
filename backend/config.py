"""
Central configuration for the Universal Review Agent backend.

Only ONE model is active at a time.
Only ONE chunking strategy is active initially.
All other options are kept as commented configuration for benchmarking.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Use absolute path so .env loads regardless of where uvicorn is launched from.
load_dotenv(Path(__file__).resolve().parent / ".env")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
SKILLS_DIR = BASE_DIR / "skills"

# Uploads live OUTSIDE backend/ on purpose: uvicorn's --reload watcher
# triggers a server restart whenever any file under the watched tree changes,
# which kills in-flight /analyze requests. Putting uploads in the project root
# avoids that without having to fiddle with --reload-exclude patterns
# (whose Windows path-separator handling is fragile).
UPLOAD_DIR = BASE_DIR.parent / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# AWS Bedrock runtime
# ---------------------------------------------------------------------------
AWS_REGION = os.getenv("AWS_REGION", "us-east-1").strip()
# Set BEDROCK_MODEL_ID in your environment to the model you want to use,
# e.g. "anthropic.claude-3-5-sonnet-20241022-v2:0"
BEDROCK_MODEL_ID = os.getenv(
    "BEDROCK_MODEL_ID",
    "REPLACE_WITH_YOUR_BEDROCK_MODEL_ID",
).strip()


# ---------------------------------------------------------------------------
# Ollama runtime
# ---------------------------------------------------------------------------
OLLAMA_HOST = "http://localhost:11434"
OLLAMA_GENERATE_ENDPOINT = f"{OLLAMA_HOST}/api/generate"
OLLAMA_TAGS_ENDPOINT = f"{OLLAMA_HOST}/api/tags"
OLLAMA_TIMEOUT_SECONDS = 600  # 10 minutes per chunk (CPU inference can be slow)


# ---------------------------------------------------------------------------
# Supported SLMs
# ---------------------------------------------------------------------------
# All four are listed so they appear in the UI dropdown. Each must be pulled
# locally via `ollama pull <id>` before it can run. The /ollama/health
# endpoint reports which are actually present.
SUPPORTED_MODELS = [
    # --- AWS Bedrock (cloud, always available when credentials are set) ---
    {
        "id": BEDROCK_MODEL_ID,
        "label": "AWS Bedrock (cloud)",
        "provider": "bedrock",
        "size_class": "cloud",
        "recommended": True,
        "active": True,
    },
    # --- 1-2B class (fast, low accuracy — useful for prompt iteration) ---
    {
        "id": "qwen2.5-coder:1.5b",
        "label": "Qwen2.5-Coder 1.5B (fast, lower accuracy)",
        "huggingface": "Qwen/Qwen2.5-Coder-1.5B-Instruct",
        "size_class": "small",
        "recommended": False,
        "active": True,
    },
    {
        "id": "deepseek-coder:1.3b",
        "label": "DeepSeek Coder 1.3B (fast, lower accuracy)",
        "huggingface": "deepseek-ai/deepseek-coder-1.3b-instruct",
        "size_class": "small",
        "recommended": False,
        "active": False,
    },
    # --- 3-4B class (balanced) ---
    {
        "id": "starcoder2:3b",
        "label": "StarCoder2 3B",
        "huggingface": "bigcode/starcoder2-3b",
        "size_class": "medium",
        "recommended": False,
        "active": False,
    },
    {
        "id": "phi3:mini",
        "label": "Phi-3 Mini 4K",
        "huggingface": "microsoft/Phi-3-mini-4k-instruct",
        "size_class": "medium",
        "recommended": False,
        "active": False,
    },
    # --- 6-7B class (recommended for serious benchmarking) ---
    {
        "id": "qwen2.5-coder:7b",
        "label": "Qwen2.5-Coder 7B (recommended for accuracy)",
        "huggingface": "Qwen/Qwen2.5-Coder-7B-Instruct",
        "size_class": "large",
        "recommended": True,
        "active": False,
    },
    {
        "id": "deepseek-coder:6.7b",
        "label": "DeepSeek Coder 6.7B (recommended for accuracy)",
        "huggingface": "deepseek-ai/deepseek-coder-6.7b-instruct",
        "size_class": "large",
        "recommended": True,
        "active": False,
    },
]

# Active by default. Switching to a 7B model gives a sizeable jump in
# instruction-following and reduces SLM-noise dramatically — see README.
ACTIVE_MODEL_ID = BEDROCK_MODEL_ID


# ---------------------------------------------------------------------------
# Chunking strategies
# ---------------------------------------------------------------------------
# IMPORTANT: file-wise chunking is NOT supported by design.
# "comprehensive" is the default and only strategy exposed to users.
# The others remain registered in the chunking registry for API-level
# benchmarking but are not shown in the UI.
SUPPORTED_CHUNKING_STRATEGIES = [
    {"id": "comprehensive", "label": "Comprehensive (all chunk types)", "active": True},
]

ACTIVE_CHUNKING_STRATEGY = "comprehensive"


# ---------------------------------------------------------------------------
# Skills
# ---------------------------------------------------------------------------
# Only static_review is implemented initially.
# Future planned skills (kept here only as configuration documentation):
#   - security_review
#   - architecture_review
#   - standards_compliance
#   - ai_detection
DEFAULT_SKILL = "static-review"

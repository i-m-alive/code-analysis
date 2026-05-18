"""
Central configuration for the Universal Review Agent backend.

Only ONE model is active at a time.
Only ONE chunking strategy is active initially.
All other options are kept as commented configuration for benchmarking.
"""

from pathlib import Path

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
    {
        "id": "qwen2.5-coder:1.5b",
        "label": "Qwen2.5-Coder 1.5B Instruct",
        "huggingface": "Qwen/Qwen2.5-Coder-1.5B-Instruct",
        "active": True,
    },
    {
        "id": "deepseek-coder:1.3b",
        "label": "DeepSeek Coder 1.3B Instruct",
        "huggingface": "deepseek-ai/deepseek-coder-1.3b-instruct",
        "active": False,
    },
    {
        "id": "starcoder2:3b",
        "label": "StarCoder2 3B",
        "huggingface": "bigcode/starcoder2-3b",
        "active": False,
    },
    {
        "id": "phi3:mini",
        "label": "Phi-3 Mini 4K Instruct",
        "huggingface": "microsoft/Phi-3-mini-4k-instruct",
        "active": False,
    },
]

ACTIVE_MODEL_ID = "qwen2.5-coder:1.5b"


# ---------------------------------------------------------------------------
# Chunking strategies
# ---------------------------------------------------------------------------
# IMPORTANT: file-wise chunking is NOT supported by design.
# All four are exposed in the UI so they can be benchmarked.
SUPPORTED_CHUNKING_STRATEGIES = [
    {"id": "function", "label": "Function-level Chunking", "active": True},
    {"id": "fixed", "label": "Fixed-size Chunking", "active": False},
    {"id": "class", "label": "Class-level Chunking", "active": False},
    {"id": "semantic", "label": "Semantic Chunking", "active": False},
]

ACTIVE_CHUNKING_STRATEGY = "function"


# ---------------------------------------------------------------------------
# Skills
# ---------------------------------------------------------------------------
# Only static_review is implemented initially.
# Future planned skills (kept here only as configuration documentation):
#   - security_review
#   - architecture_review
#   - standards_compliance
#   - ai_detection
DEFAULT_SKILL = "static_review"

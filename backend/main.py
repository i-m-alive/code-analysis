"""
FastAPI entry point for the Universal Review Agent.

Run with:
    uvicorn main:app --reload
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
# All Universal-Review-Agent code uses `logging.getLogger("ura")` (or a child
# logger like "ura.agent"). We configure a single handler here so log lines
# show up in the uvicorn terminal with a clear prefix and timestamp.
LOG_FORMAT = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, datefmt="%H:%M:%S")
# Keep our own logger at DEBUG so per-chunk progress is visible without
# turning up uvicorn/httpx noise.
logging.getLogger("ura").setLevel(logging.DEBUG)
# Silence httpx's per-request INFO lines — they're noisy during SLM loops.
logging.getLogger("httpx").setLevel(logging.WARNING)

from routers import analyze, chunking, models, ollama, skills, upload  # noqa: E402

app = FastAPI(
    title="Universal Review Agent",
    description=(
        "Local AI-powered source code review system using LangGraph "
        "orchestration and LangChain model adapters. Skill-based, modular, "
        "single-agent architecture."
    ),
    version="0.1.0",
)

# CORS for the Vite dev server. Wide-open during local experimentation.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {
        "service": "Universal Review Agent",
        "status": "ok",
        "endpoints": [
            "/upload",
            "/analyze",
            "/models",
            "/chunking-strategies",
            "/skills",
            "/ollama/health",
        ],
    }


app.include_router(upload.router)
app.include_router(analyze.router)
app.include_router(models.router)
app.include_router(chunking.router)
app.include_router(skills.router)
app.include_router(ollama.router)

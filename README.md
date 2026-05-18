# Universal Review Agent

Local AI-powered source code review system for benchmarking small language
models (SLMs), chunking strategies, and static-review capabilities.

This is a **single-agent**, skill-based architecture. There is no
multi-agent orchestration, no MCP server, no LangGraph / CrewAI / AutoGen,
no vector DB, and no embeddings.

## Architecture

```
User Upload
    ↓
Ingestion Agent
    ├── File Parsing
    ├── Language Detection
    └── Chunking          (function | fixed | class | semantic)
            ↓
Prepared Chunks
            ↓
Universal Review Agent
            ↓
Dynamic Skill Loader      (loads skills/<name>/ at runtime)
            ↓
Static Review Skill
    ├── SKILL.md
    ├── Deterministic Scripts (naming, complexity, dead-code, imports, format)
    ├── Resources             (pep8_rules.json, naming_rules.json)
    └── Templates             (output_schema.json)
            ↓
SLM Inference             (Ollama → Qwen2.5-Coder 1.5B)
            ↓
Structured Findings (JSON)
            ↓
React Frontend
```

## Folder layout

```
code analysis/
├── backend/
│   ├── main.py
│   ├── config.py
│   ├── requirements.txt
│   ├── agents/
│   │   ├── ingestion_agent.py
│   │   └── universal_review_agent.py
│   ├── chunking/
│   │   ├── base.py
│   │   ├── function_chunker.py        # active
│   │   ├── fixed_chunker.py           # commented
│   │   ├── class_chunker.py           # commented
│   │   └── semantic_chunker.py        # commented
│   ├── llm/ollama_client.py
│   ├── skill_loader/loader.py
│   ├── routers/
│   │   ├── upload.py
│   │   ├── analyze.py
│   │   ├── models.py
│   │   ├── chunking.py
│   │   └── skills.py
│   ├── models/schemas.py
│   ├── utils/file_utils.py
│   └── skills/
│       └── static_review/
│           ├── SKILL.md
│           ├── prompts/review_prompt.txt
│           ├── scripts/
│           │   ├── naming_checker.py
│           │   ├── complexity_checker.py
│           │   ├── dead_code_checker.py
│           │   ├── unused_import_checker.py
│           │   └── formatting_checker.py
│           ├── resources/
│           │   ├── pep8_rules.json
│           │   └── naming_rules.json
│           └── templates/output_schema.json
└── frontend/
    ├── package.json
    ├── vite.config.js
    ├── index.html
    └── src/
        ├── main.jsx
        ├── App.jsx
        ├── App.css
        ├── api/client.js
        └── components/{Header,FileUploader,Selectors,FindingsTable}.jsx
```

## Prerequisites

1. **Python 3.10+**
2. **Node.js 18+**
3. **Ollama** running locally:
   ```
   ollama pull qwen2.5-coder:1.5b
   ollama serve
   ```
   Other models in `backend/config.py` are commented out — uncomment and
   pull them to benchmark alternatives:
   - `deepseek-coder:1.3b`
   - `starcoder2:3b`
   - `phi3:mini`

## Run

### Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --reload
```

> Uploaded files are stored in `uploads/` at the **project root** (not under
> `backend/`). This is intentional so uvicorn's auto-reload doesn't restart
> the server when a new file is uploaded mid-request.

Backend listens on `http://localhost:8000`.

### Frontend

```powershell
cd frontend
npm install
npm run dev
```

Frontend runs on `http://localhost:5173` and proxies `/api/*` to the backend.

## API

| Method | Endpoint                | Purpose                                |
|--------|-------------------------|----------------------------------------|
| POST   | `/upload`               | Upload one or more source files        |
| POST   | `/analyze`              | Run the Universal Review Agent         |
| GET    | `/models`               | List supported SLMs and active model   |
| GET    | `/chunking-strategies`  | List chunking strategies and active    |
| GET    | `/skills`               | List skills on disk                    |
| GET    | `/skills/{name}`        | Inspect a single skill                 |

### `/analyze` response shape

```json
{
  "model": "qwen2.5-coder:1.5b",
  "chunking_strategy": "function",
  "skill": "static_review",
  "results": [
    {
      "file_name": "sample.py",
      "chunk_id": "sample.py::foo#4",
      "chunk_type": "function",
      "language": "python",
      "start_line": 4,
      "end_line": 11,
      "code": "...",
      "model": "qwen2.5-coder:1.5b",
      "chunking_strategy": "function",
      "skill": "static_review",
      "issues": [
        {
          "severity": "high",
          "line": "7",
          "issue": "Deep nesting detected (depth=5, max allowed=4)",
          "recommendation": "Refactor using early returns",
          "source": "deterministic"
        }
      ]
    }
  ]
}
```

## Design rules

1. Deterministic scripts produce **measurable** findings.
2. The SLM only adds **reasoning, prioritization and human-friendly recommendations**.
3. Skills are loaded **dynamically by folder name**. The agent has zero
   hardcoded knowledge of static review, security review, etc.
4. **Only function chunking** is active. Other strategies are scaffolded
   but commented in `chunking/__init__.py` for benchmark switching.
5. **Only one model is active at a time.** Switch by changing
   `ACTIVE_MODEL_ID` in `backend/config.py`.
6. No databases, vector DBs, RAG, embeddings, LangChain, MCP, or multi-agent
   orchestration. Everything runs locally.

## Adding a new skill

Drop a new directory under `backend/skills/` matching this shape:

```
skills/security_review/
├── SKILL.md
├── prompts/review_prompt.txt
├── scripts/*.py                # each exposes `def run(chunk, resources) -> list[dict]`
├── resources/*.json
└── templates/output_schema.json
```

It will appear automatically in `GET /skills` and become selectable in the UI.
No agent code changes required.

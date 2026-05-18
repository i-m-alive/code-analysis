"""
Pydantic schemas used by the API layer.

Kept intentionally minimal — these mirror the output JSON contract specified
in the project brief so the frontend can render results directly.
"""

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class Issue(BaseModel):
    severity: str = Field(..., description="info | low | medium | high | critical")
    line: str = Field(..., description="Line number(s) where issue occurs")
    issue: str = Field(..., description="Short description of the issue")
    recommendation: str = Field(..., description="How to fix it")
    source: Optional[str] = Field(
        default=None,
        description="Origin of the finding: 'deterministic' or 'slm'",
    )
    category: Optional[str] = Field(
        default=None,
        description="correctness | security | maintainability | performance | style",
    )


class ChunkReview(BaseModel):
    file_name: str
    chunk_id: str
    chunk_type: str = Field(..., description="function | class | fixed | semantic")
    language: str
    start_line: int
    end_line: int
    code: str
    model: str
    chunking_strategy: str
    skill: str
    issues: List[Issue] = []


class AnalyzeRequest(BaseModel):
    # `model_id` collides with Pydantic v2's protected `model_` namespace;
    # disable the protection so the field name can stay user-friendly.
    model_config = ConfigDict(protected_namespaces=())

    file_ids: List[str]
    model_id: Optional[str] = None
    chunking_strategy: Optional[str] = None
    skill: Optional[str] = None


class UploadedFile(BaseModel):
    file_id: str
    file_name: str
    size_bytes: int
    language: str


class AnalyzeResponse(BaseModel):
    model: str
    chunking_strategy: str
    skill: str
    results: List[ChunkReview]

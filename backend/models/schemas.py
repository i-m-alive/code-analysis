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
    confidence: Optional[int] = Field(
        default=None,
        ge=0,
        le=100,
        description="SLM self-confidence 0-100 (only present on SLM findings)",
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


class TopIssue(BaseModel):
    issue: str
    count: int


class AspectScore(BaseModel):
    name: str = Field(..., description="correctness | security | maintainability | performance | style")
    weight: float
    score: float = Field(..., ge=0, le=100)
    grade: str
    issue_count: int
    severity_breakdown: dict
    top_issues: List[TopIssue] = []
    annotation: str


class OverallScore(BaseModel):
    score: float = Field(..., ge=0, le=100)
    grade: str
    annotation: str


class Scoring(BaseModel):
    overall: OverallScore
    aspects: List[AspectScore]
    metadata: dict


class AnalyzeResponse(BaseModel):
    model: str
    chunking_strategy: str
    skill: str
    results: List[ChunkReview]
    scoring: Optional[Scoring] = None

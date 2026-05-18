"""
GET /skills — list all skills available on disk (one folder per skill).

GET /skills/{name} — return metadata for a single skill (SKILL.md content,
script names, resource keys).
"""

from fastapi import APIRouter, HTTPException

from config import DEFAULT_SKILL
from skill_loader.loader import list_skills, load_skill

router = APIRouter()


@router.get("/skills")
def skills() -> dict:
    return {
        "default": DEFAULT_SKILL,
        "skills": list_skills(),
    }


@router.get("/skills/{name}")
def skill_detail(name: str) -> dict:
    try:
        loaded = load_skill(name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return {
        "name": loaded.name,
        "description": loaded.description,
        "scripts": [{"name": s.name, "description": s.description.strip()} for s in loaded.scripts],
        "resources": sorted(loaded.resources.keys()),
        "output_schema": loaded.output_schema,
    }

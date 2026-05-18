"""
Dynamic skill loader.

A "skill" is a self-contained directory on disk shaped like:

    skills/<skill_name>/
        SKILL.md
        prompts/review_prompt.txt
        scripts/*.py
        resources/*.json
        templates/output_schema.json

The agent never imports skills by name — it loads them by path. This keeps
the agent generic so we can drop in `security_review`, `architecture_review`,
etc. without touching the agent.

Scripts are loaded via importlib.util.spec_from_file_location so the loader
doesn't require the skill directory to be on sys.path.
"""

import importlib.util
import json
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Callable, List

from config import SKILLS_DIR


@dataclass
class LoadedSkill:
    name: str
    path: Path
    description: str
    system_prompt: str
    prompt_template: str
    output_schema: dict
    resources: dict = field(default_factory=dict)
    scripts: List["LoadedScript"] = field(default_factory=list)


@dataclass
class LoadedScript:
    name: str
    module: ModuleType
    run: Callable
    description: str


def list_skills() -> List[str]:
    if not SKILLS_DIR.exists():
        return []
    return sorted(p.name for p in SKILLS_DIR.iterdir() if p.is_dir())


def load_skill(skill_name: str) -> LoadedSkill:
    skill_path = SKILLS_DIR / skill_name
    if not skill_path.is_dir():
        raise FileNotFoundError(f"Skill not found: {skill_name}")

    skill_md = skill_path / "SKILL.md"
    description = skill_md.read_text(encoding="utf-8") if skill_md.exists() else ""

    prompt_file = skill_path / "prompts" / "review_prompt.txt"
    prompt_template = (
        prompt_file.read_text(encoding="utf-8") if prompt_file.exists() else ""
    )

    schema_file = skill_path / "templates" / "output_schema.json"
    output_schema = (
        json.loads(schema_file.read_text(encoding="utf-8"))
        if schema_file.exists()
        else {}
    )

    # Load every JSON file under resources/ keyed by stem name.
    resources: dict = {}
    resources_dir = skill_path / "resources"
    if resources_dir.is_dir():
        for f in resources_dir.glob("*.json"):
            try:
                resources[f.stem] = json.loads(f.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                resources[f.stem] = {}

    # Dynamically import every *.py file under scripts/ that exposes a run().
    scripts: List[LoadedScript] = []
    scripts_dir = skill_path / "scripts"
    if scripts_dir.is_dir():
        for f in sorted(scripts_dir.glob("*.py")):
            if f.name.startswith("_"):
                continue
            module = _load_module(f)
            run_fn = getattr(module, "run", None)
            if not callable(run_fn):
                continue
            scripts.append(
                LoadedScript(
                    name=f.stem,
                    module=module,
                    run=run_fn,
                    description=getattr(module, "__doc__", "") or "",
                )
            )

    system_prompt = (
        f"You are the {skill_name} reviewer. Follow the skill instructions "
        f"and respond ONLY with JSON conforming to the provided schema."
    )

    return LoadedSkill(
        name=skill_name,
        path=skill_path,
        description=description,
        system_prompt=system_prompt,
        prompt_template=prompt_template,
        output_schema=output_schema,
        resources=resources,
        scripts=scripts,
    )


def _load_module(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"skill_script_{path.stem}", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load skill script: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

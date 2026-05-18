# Static Review Skill

## Purpose
Perform deterministic static analysis on a single code chunk and produce
structured findings. The deterministic scripts in `scripts/` are the source
of truth for measurable issues; the SLM is only asked to add reasoning,
prioritize, and write human-friendly recommendations.

## Inputs
The loader passes the following to each `run(chunk, resources)` function:
- `chunk`: dict with keys `code`, `language`, `start_line`, `end_line`, `name`
- `resources`: dict of loaded JSON resources (e.g. `pep8_rules`, `naming_rules`)

## Outputs
Each script returns a list of findings:
```json
[
  {
    "severity": "low|medium|high|critical|info",
    "line": "12",
    "issue": "Short description",
    "recommendation": "How to fix"
  }
]
```

## Responsibilities
- Validate naming conventions
- Detect deep nesting / high complexity
- Detect unused imports
- Detect dead code
- Validate formatting (PEP8-style)
- Provide severity and line numbers
- Generate human-friendly recommendations (added by SLM)

## SLM Role
The SLM receives:
1. The original code chunk
2. The aggregated deterministic findings
3. The output JSON schema

and is asked to:
- Confirm / refine each finding
- Add brief reasoning
- Surface any additional issues the deterministic scripts may have missed
- Emit final structured JSON matching `templates/output_schema.json`

"""
Scoring for the `static_review` skill.

Aggregates the per-chunk findings produced by the deterministic + SLM
pipeline into:

- Per-aspect scores (0–100) for correctness, security, maintainability,
  performance, style
- A weighted overall score and letter grade
- Human-readable annotations explaining what drove each score and where to
  focus first

The scorer is **deterministic** — it does not call the SLM. Every future
skill (security_review, architecture_review, …) can ship its own
`scoring.py` with its own categories, weights, and annotation logic; the
loader picks it up automatically.

Entry point: `run(results, resources) -> dict` matching the `Scoring`
Pydantic schema.
"""

import math
from collections import Counter
from typing import Dict, List

# ---------------------------------------------------------------------------
# Configuration — tweak these to recalibrate scoring without touching code.
# ---------------------------------------------------------------------------

# How much each aspect contributes to the overall score. Should sum to ~1.0.
ASPECT_WEIGHTS: Dict[str, float] = {
    "correctness":     0.30,
    "security":        0.25,
    "maintainability": 0.20,
    "performance":     0.15,
    "style":           0.10,
}

# Penalty (points deducted from 100) per finding, before normalization.
# Calibrated so a function with one HIGH finding can't score >90 in its
# aspect, and a function with one CRITICAL can't score >80.
SEVERITY_PENALTY = {
    "critical": 40.0,
    "high":     20.0,
    "medium":     7.0,
    "low":        2.0,
    "info":       0.5,
}

# Normalize using sqrt(lines/100) — small files get full weight; larger
# codebases are dampened, but never become "free" the way linear /N would
# make them. e.g. 100 lines → denom 1.0, 400 lines → 2.0, 10 000 lines → 10.
NORMALIZE_PER_LINES = 100

# Findings without a `category` are assumed to be maintainability concerns
# (long functions, deep nesting, unused imports, etc.).
DEFAULT_CATEGORY = "maintainability"


# ---------------------------------------------------------------------------
# Grade table — based on the final 0–100 score.
# ---------------------------------------------------------------------------

def _grade(score: float) -> str:
    if score >= 95: return "A+"
    if score >= 90: return "A"
    if score >= 85: return "A-"
    if score >= 80: return "B+"
    if score >= 75: return "B"
    if score >= 70: return "C+"
    if score >= 65: return "C"
    if score >= 60: return "D+"
    if score >= 50: return "D"
    return "F"


# ---------------------------------------------------------------------------
# Annotation generators (deterministic, no SLM)
# ---------------------------------------------------------------------------

def _aspect_annotation(name: str, score: float, sev: dict, top: List[dict]) -> str:
    crit_high = sev.get("critical", 0) + sev.get("high", 0)
    primary = top[0]["issue"] if top else None

    if score >= 95:
        return f"Excellent {name}. No notable issues."

    if score >= 85:
        return (f"Strong {name}. Minor polish remains "
                f"({sev.get('low', 0) + sev.get('info', 0)} low/info items).")

    if score >= 70:
        if primary:
            return (f"Good {name} with focused improvements available. "
                    f"Most common issue: '{primary[:55]}…' "
                    f"({crit_high} high+ severity).")
        return f"Good {name}. A handful of medium-severity items to address."

    if score >= 50:
        if primary:
            return (f"Notable {name} debt — {crit_high} high/critical items. "
                    f"Top pattern: '{primary[:55]}…'. Address this cluster first.")
        return f"Notable {name} debt. Prioritize the {crit_high} high-severity findings."

    if primary:
        return (f"Significant {name} concerns ({crit_high} high+). "
                f"Refactor recommended before adding features. "
                f"Worst pattern: '{primary[:55]}…'.")
    return f"Significant {name} concerns. Refactor recommended."


def _overall_annotation(score: float, aspects: List[dict]) -> str:
    if not aspects:
        return "No findings to assess."

    best = max(aspects, key=lambda a: a["score"])
    worst = min(aspects, key=lambda a: a["score"])

    if score >= 90:
        return (f"Excellent overall code quality. Strongest: {best['name']} "
                f"({best['score']:.0f}). Maintain current standards.")

    if score >= 75:
        return (f"Solid code with room to improve. Focus on {worst['name']} "
                f"({worst['score']:.0f}/100) before other areas.")

    if score >= 60:
        crit_high = (worst['severity_breakdown'].get('critical', 0)
                     + worst['severity_breakdown'].get('high', 0))
        return (f"Multiple quality concerns. Primary focus: {worst['name']} "
                f"({worst['score']:.0f}/100). Address {crit_high} "
                f"high-severity items first.")

    return (f"Significant technical debt. {worst['name']} is most damaged "
            f"({worst['score']:.0f}/100). Consider a focused refactor before "
            f"adding new features.")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _effective_lines_of_chunk(chunk_review: dict) -> int:
    """Cheap approximation: count non-blank, non-comment-only lines."""
    code = chunk_review.get("code", "") or ""
    count = 0
    for line in code.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            continue
        count += 1
    return max(1, count)


def _bucket_for(category: str) -> str:
    cat = (category or "").lower()
    if cat in ASPECT_WEIGHTS:
        return cat
    return DEFAULT_CATEGORY


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run(results: List[dict], resources: dict) -> dict:
    """
    Aggregate scoring across all chunk reviews.

    Args:
        results: list of chunk-review dicts (the same shape returned by
                 UniversalReviewAgent.review_chunk).
        resources: skill resources (currently unused but kept for parity
                   with the deterministic-script signature).
    """
    # --- 1) Aggregate per-aspect data ---------------------------------------
    aspect_data: Dict[str, dict] = {
        a: {
            "penalty": 0.0,
            "issue_count": 0,
            "severity": {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0},
            "issues_text": [],
        }
        for a in ASPECT_WEIGHTS
    }

    total_effective_lines = 0
    for chunk_review in results:
        total_effective_lines += _effective_lines_of_chunk(chunk_review)
        for issue in chunk_review.get("issues", []) or []:
            severity = (issue.get("severity") or "info").lower()
            bucket = _bucket_for(issue.get("category"))
            penalty = SEVERITY_PENALTY.get(severity, 0.0)

            data = aspect_data[bucket]
            data["penalty"] += penalty
            data["issue_count"] += 1
            if severity in data["severity"]:
                data["severity"][severity] += 1
            issue_text = (issue.get("issue") or "").strip()
            if issue_text:
                data["issues_text"].append(issue_text[:80])

    # --- 2) sqrt-normalize and compute scores -------------------------------
    # sqrt(lines/100): small files get full weight, big codebases dampen
    # gently — but never collapse to "free penalty" the way linear /N does.
    denominator = max(1.0, math.sqrt(total_effective_lines / NORMALIZE_PER_LINES))

    aspects: List[dict] = []
    weighted_sum = 0.0
    weight_total = 0.0

    for name, weight in ASPECT_WEIGHTS.items():
        data = aspect_data[name]
        normalized_penalty = data["penalty"] / denominator
        score = max(0.0, min(100.0, 100.0 - normalized_penalty))

        # Top recurring issue strings for this aspect (deterministic).
        counter: Counter = Counter(data["issues_text"])
        top_issues = [
            {"issue": txt, "count": cnt}
            for txt, cnt in counter.most_common(3)
        ]

        aspects.append({
            "name": name,
            "weight": round(weight, 3),
            "score": round(score, 1),
            "grade": _grade(score),
            "issue_count": data["issue_count"],
            "severity_breakdown": dict(data["severity"]),
            "top_issues": top_issues,
            "annotation": _aspect_annotation(name, score, data["severity"], top_issues),
        })
        weighted_sum += score * weight
        weight_total += weight

    overall_score = (weighted_sum / weight_total) if weight_total else 100.0
    overall = {
        "score": round(overall_score, 1),
        "grade": _grade(overall_score),
        "annotation": _overall_annotation(overall_score, aspects),
    }

    metadata = {
        "total_chunks": len(results),
        "total_issues": sum(a["issue_count"] for a in aspects),
        "effective_lines": total_effective_lines,
        "weights": ASPECT_WEIGHTS,
        "severity_penalty": SEVERITY_PENALTY,
        "normalize_per_lines": NORMALIZE_PER_LINES,
    }

    return {
        "overall": overall,
        "aspects": aspects,
        "metadata": metadata,
    }

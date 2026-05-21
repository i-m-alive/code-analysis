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

Scoring improvements (v2):

  Fix 1 — Confidence-gated penalties
    SLM findings are weighted by their reported confidence field (0–100).
    Deterministic rule-based findings always carry full weight (1.0).
    This stops a chatty-but-uncertain model from driving scores to zero
    while a silent model scores 100.

  Fix 2 — Intra-chunk deduplication
    If a deterministic rule and an SLM finding flag the same line for the
    same reason, the SLM duplicate is discarded before scoring. Prevents
    the same bug from being double-counted (and double-penalised).

  Fix 3 — Piecewise tanh curve
    The old linear `score = 100 − penalty` formula collapses to 0 for any
    code with enough findings, making a thorough model look worse than a
    silent one. We keep the linear region for low-penalty code and switch
    to a diminishing-returns tanh curve beyond CURVE_INFLECTION points so
    that scores stay meaningful and differentiating even for very buggy files.

Entry point: `run(results, resources) -> dict` matching the `Scoring`
Pydantic schema.
"""

import math
from collections import Counter
from typing import Dict, List

# ---------------------------------------------------------------------------
# Configuration — tweak these to recalibrate scoring without touching logic.
# ---------------------------------------------------------------------------

# How much each aspect contributes to the overall score. Should sum to ~1.0.
ASPECT_WEIGHTS: Dict[str, float] = {
    "correctness":     0.30,
    "security":        0.25,
    "maintainability": 0.20,
    "performance":     0.15,
    "style":           0.10,
}

# Base penalty (points) per finding, before confidence weighting and
# normalization. Deterministic findings always apply the full base penalty.
SEVERITY_PENALTY = {
    "critical": 40.0,
    "high":     20.0,
    "medium":    7.0,
    "low":       2.0,
    "info":      0.5,
}

# Normalize using sqrt(lines/100) so small files get full weight and large
# codebases are dampened, but never become "free" the way linear /N would.
NORMALIZE_PER_LINES = 100

# Issues without a recognised `category` are bucketed here.
DEFAULT_CATEGORY = "maintainability"

# --- Fix 1: Confidence gating ----------------------------------------------
# Deterministic findings: weight = 1.0 (always).
# SLM findings: weight = confidence / 100, clamped to [FLOOR, 1.0].
# When the `confidence` field is absent we assume SLM_DEFAULT_CONFIDENCE.
SLM_CONFIDENCE_FLOOR    = 0.50   # even 0%-confidence SLM cost 50% of penalty
SLM_DEFAULT_CONFIDENCE  = 70     # assumed confidence when field is absent

# --- Fix 3: Piecewise curve ------------------------------------------------
# Linear for penalty ≤ CURVE_INFLECTION (same behaviour as v1 for good code).
# Tanh-based diminishing returns for the tail (scores never truly hit 0).
#
#   penalty =   0  →  score 100
#   penalty =  50  →  score  50  (inflection, continuous with linear)
#   penalty =  83  →  score  ~30
#   penalty = 116  →  score  ~16
#   penalty = 200  →  score   ~1
CURVE_INFLECTION = 50.0   # breakpoint between linear and diminishing regions
CURVE_TANH_SCALE = 80.0   # higher = softer curve; lower = harder saturation


# ---------------------------------------------------------------------------
# Grade table
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
# Fix 1: Source-confidence weight
# ---------------------------------------------------------------------------

def _source_weight(issue: dict) -> float:
    """
    Return a [SLM_CONFIDENCE_FLOOR, 1.0] multiplier for a single finding.

    Deterministic findings always return 1.0.
    SLM findings are scaled by their confidence / 100, with a floor so that
    even very low-confidence findings still contribute a minimum penalty.
    """
    if (issue.get("source") or "").lower() == "deterministic":
        return 1.0
    raw = issue.get("confidence")
    conf = raw if raw is not None else SLM_DEFAULT_CONFIDENCE
    return max(SLM_CONFIDENCE_FLOOR, min(1.0, conf / 100.0))


# ---------------------------------------------------------------------------
# Fix 2: Intra-chunk deduplication
# ---------------------------------------------------------------------------

def _deduplicate_issues(issues: List[dict]) -> List[dict]:
    """
    Remove SLM findings that duplicate a deterministic one in the same chunk.

    Two findings are considered duplicates when they share the same line
    number and the first 35 characters of their issue text match
    (case-insensitive).  The deterministic finding is kept; the SLM
    duplicate is discarded.

    Returns the deduplicated issue list (deterministic first, then SLM).
    """
    deterministic = [i for i in issues if (i.get("source") or "").lower() == "deterministic"]
    slm_issues    = [i for i in issues if (i.get("source") or "").lower() != "deterministic"]

    det_keys = {
        (str(i.get("line") or ""), (i.get("issue") or "").lower().strip()[:35])
        for i in deterministic
    }

    kept_slm = [
        i for i in slm_issues
        if (str(i.get("line") or ""), (i.get("issue") or "").lower().strip()[:35])
           not in det_keys
    ]

    return deterministic + kept_slm


# ---------------------------------------------------------------------------
# Fix 3: Piecewise score curve
# ---------------------------------------------------------------------------

def _apply_curve(normalized_penalty: float) -> float:
    """
    Map a normalised penalty value to a 0–100 score.

    Linear region  (penalty ≤ CURVE_INFLECTION):
        score = 100 - penalty
        Identical to the v1 formula — well-behaved code is unaffected.

    Diminishing-returns region  (penalty > CURVE_INFLECTION):
        score = CURVE_INFLECTION × (1 - tanh(tail / CURVE_TANH_SCALE))
        Ensures that adding more findings always lowers the score, but the
        score approaches 0 asymptotically rather than snapping there.
    """
    if normalized_penalty <= CURVE_INFLECTION:
        return 100.0 - normalized_penalty
    tail = normalized_penalty - CURVE_INFLECTION
    return CURVE_INFLECTION * (1.0 - math.tanh(tail / CURVE_TANH_SCALE))


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

    best  = max(aspects, key=lambda a: a["score"])
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
    count = sum(
        1 for line in code.splitlines()
        if line.strip() and not line.strip().startswith("#")
    )
    return max(1, count)


def _bucket_for(category: str) -> str:
    cat = (category or "").lower()
    return cat if cat in ASPECT_WEIGHTS else DEFAULT_CATEGORY


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run(results: List[dict], resources: dict) -> dict:
    """
    Aggregate scoring across all chunk reviews.

    Args:
        results:   list of chunk-review dicts (same shape returned by
                   UniversalReviewAgent.review_chunk).
        resources: skill resources (currently unused but kept for parity
                   with the deterministic-script signature).
    """
    aspect_data: Dict[str, dict] = {
        a: {
            "penalty":     0.0,
            "issue_count": 0,
            "severity":    {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0},
            "issues_text": [],
        }
        for a in ASPECT_WEIGHTS
    }

    total_effective_lines = 0
    total_raw_issues      = 0
    total_deduped         = 0

    for chunk_review in results:
        total_effective_lines += _effective_lines_of_chunk(chunk_review)

        raw_issues = chunk_review.get("issues", []) or []
        total_raw_issues += len(raw_issues)

        # Fix 2: drop SLM duplicates of deterministic findings
        deduped = _deduplicate_issues(raw_issues)
        total_deduped += len(raw_issues) - len(deduped)

        for issue in deduped:
            severity = (issue.get("severity") or "info").lower()
            bucket   = _bucket_for(issue.get("category"))

            # Fix 1: scale base penalty by source confidence
            base    = SEVERITY_PENALTY.get(severity, 0.0)
            weight  = _source_weight(issue)
            penalty = base * weight

            data = aspect_data[bucket]
            data["penalty"]     += penalty
            data["issue_count"] += 1
            if severity in data["severity"]:
                data["severity"][severity] += 1
            issue_text = (issue.get("issue") or "").strip()
            if issue_text:
                data["issues_text"].append(issue_text[:80])

    # sqrt(lines/100): small files get full weight, large codebases dampen gently
    denominator = max(1.0, math.sqrt(total_effective_lines / NORMALIZE_PER_LINES))

    aspects: List[dict] = []
    weighted_sum = 0.0
    weight_total = 0.0

    for name, weight in ASPECT_WEIGHTS.items():
        data = aspect_data[name]
        normalized_penalty = data["penalty"] / denominator

        # Fix 3: piecewise curve instead of hard linear clamp
        score = max(0.0, min(100.0, _apply_curve(normalized_penalty)))

        counter: Counter = Counter(data["issues_text"])
        top_issues = [
            {"issue": txt, "count": cnt}
            for txt, cnt in counter.most_common(3)
        ]

        aspects.append({
            "name":               name,
            "weight":             round(weight, 3),
            "score":              round(score, 1),
            "grade":              _grade(score),
            "issue_count":        data["issue_count"],
            "severity_breakdown": dict(data["severity"]),
            "top_issues":         top_issues,
            "annotation":         _aspect_annotation(name, score, data["severity"], top_issues),
        })
        weighted_sum += score * weight
        weight_total += weight

    overall_score = (weighted_sum / weight_total) if weight_total else 100.0
    overall = {
        "score":      round(overall_score, 1),
        "grade":      _grade(overall_score),
        "annotation": _overall_annotation(overall_score, aspects),
    }

    metadata = {
        "total_chunks":          len(results),
        "total_issues":          sum(a["issue_count"] for a in aspects),
        "issues_deduplicated":   total_deduped,
        "effective_lines":       total_effective_lines,
        "weights":               ASPECT_WEIGHTS,
        "severity_penalty":      SEVERITY_PENALTY,
        "normalize_per_lines":   NORMALIZE_PER_LINES,
        "scoring_v2": {
            "confidence_gating":      True,
            "intra_chunk_dedup":      True,
            "tanh_curve":             True,
            "slm_confidence_floor":   SLM_CONFIDENCE_FLOOR,
            "slm_default_confidence": SLM_DEFAULT_CONFIDENCE,
            "curve_inflection":       CURVE_INFLECTION,
            "curve_tanh_scale":       CURVE_TANH_SCALE,
        },
    }

    return {
        "overall":  overall,
        "aspects":  aspects,
        "metadata": metadata,
    }

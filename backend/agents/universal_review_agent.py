"""
Universal Review Agent
======================
A SINGLE agent (not multi-agent) that:

1. Loads a skill dynamically by name.
2. Runs every deterministic script in that skill against a chunk.
3. Builds a prompt from the skill's prompt template + deterministic findings.
4. Calls the active SLM via Ollama.
5. Sanitizes the SLM output through a sanity-gate (line range, phrase blacklist,
   unused-var verification, code-quote verification, confidence threshold,
   "X is not defined" hallucination check, bogus magic-number rejection).
6. Merges deterministic + SLM findings with fuzzy de-duplication.

The agent itself has NO hardcoded knowledge of static review, security
review, etc. — all rules live inside the skill folder.
"""

import json
import logging
import re
import time
from dataclasses import asdict
from typing import List, Optional, Tuple

from chunking.base import CodeChunk
from llm.ollama_client import OllamaError, generate, safe_json_extract
from skill_loader.loader import LoadedSkill, load_skill

logger = logging.getLogger("ura.agent")


# ---------------------------------------------------------------------------
# SLM sanity-gate constants
# ---------------------------------------------------------------------------

# Common defaults the SLM tends to flag as "magic numbers" — they aren't.
_BOGUS_MAGIC_TOKENS = ("0.0", "1.0", "-1.0", "(0)", "(1)", "(-1)", "== 0", "== 1")

# Phrases that almost always indicate Qwen-1.5B-class SLM hallucination.
# These are derived from empirical analysis of real review runs — every match
# we observed was a false positive, so we hard-reject them.
_BAD_PHRASES = (
    "does not handle",
    "doesn't handle",
    "not initialized before",
    "is not initialized",
    "not used after",
    "is not provided",
    "are not provided",
    "fails to handle",
    "does not check",
    "doesn't check",
    "missing docstring",          # too noisy on FastAPI-style handlers
    "missing type hint",          # ditto
    "should be used instead of",  # tautological SLM noise
)

# Patterns to extract a variable name from SLM "unused variable" claims.
# Cover both orderings: "parameter X is not used" AND "X parameter is not used".
_UNUSED_VAR_PATTERNS = (
    re.compile(
        r"(?:variable|parameter|local|argument)\s+[`'\"]?([A-Za-z_][\w]*)[`'\"]?"
        r"\s+(?:is\s+not|not|isn'?t)\s+(?:used|initialized|referenced)",
        re.IGNORECASE,
    ),
    re.compile(
        r"[`'\"]?([A-Za-z_][\w]*)[`'\"]?\s+(?:variable|parameter|local|argument)\s+"
        r"(?:is\s+not|not|isn'?t)\s+(?:used|initialized|referenced)",
        re.IGNORECASE,
    ),
    re.compile(
        r"unused\s+(?:variable|parameter|local|argument)\s+[`'\"]?([A-Za-z_][\w.]*)[`'\"]?",
        re.IGNORECASE,
    ),
    re.compile(
        r"[`'\"]?([A-Za-z_][\w]*)[`'\"]?\s+is\s+(?:declared\s+but\s+)?never\s+(?:used|read|referenced)",
        re.IGNORECASE,
    ),
    re.compile(
        r"remove\s+the\s+unused\s+[`'\"]?([A-Za-z_][\w]*)[`'\"]?",
        re.IGNORECASE,
    ),
)

# Bogus magic-number references: the literal *value* being flagged.
_BOGUS_MAGIC_VALUES = {"0", "1", "-1", "0.0", "1.0", "-1.0"}

# English stopwords that our regexes can spuriously capture as variable names
# (e.g. "is", "the"). Skip these when checking unused-var claims.
_NAMING_STOPWORDS = {
    "is", "are", "was", "were", "be", "been", "being", "not", "no",
    "the", "a", "an", "it", "this", "that", "these", "those",
    "to", "of", "in", "and", "or", "if", "else", "for", "while",
}

# Extract backtick-quoted code tokens (e.g. ``== False``, ``send_email``).
_BACKTICK_RE = re.compile(r"`([^`\n]{1,80})`")

# Detect FastAPI / Pydantic dependency-injected parameters that always look
# "unused" but have side effects (auth, body parsing, etc.).
def _is_dependency_param(var_name: str, code: str) -> bool:
    pattern = re.compile(
        rf"\b{re.escape(var_name)}\s*(?::\s*[^=,)\n]+)?\s*=\s*"
        rf"(?:Depends|Body|Query|Header|Path|Cookie|File|Form|Security)\s*\(",
        re.IGNORECASE,
    )
    return bool(pattern.search(code))


def _word_occurrences(name: str, code: str) -> int:
    return len(re.findall(rf"\b{re.escape(name)}\b", code))


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class UniversalReviewAgent:
    def __init__(self, skill_name: str):
        self.skill: LoadedSkill = load_skill(skill_name)
        logger.info(
            "Loaded skill '%s' | %d deterministic script(s)",
            self.skill.name,
            len(self.skill.scripts),
        )

    # -------------------------------------------------------------------
    # Deterministic stage
    # -------------------------------------------------------------------
    def _run_deterministic(self, chunk_dict: dict) -> List[dict]:
        findings: List[dict] = []
        for script in self.skill.scripts:
            try:
                result = script.run(chunk_dict, self.skill.resources)
                if isinstance(result, list):
                    for item in result:
                        if isinstance(item, dict):
                            item.setdefault("source", "deterministic")
                            findings.append(item)
            except Exception as exc:
                logger.warning("    script '%s' raised: %s", script.name, exc)
                findings.append({
                    "severity": "info",
                    "line": str(chunk_dict.get("start_line", 1)),
                    "issue": f"Script '{script.name}' failed: {exc}",
                    "recommendation": "Investigate the deterministic script.",
                    "source": "deterministic",
                })
        logger.info("    deterministic: %d finding(s)", len(findings))
        return findings

    # -------------------------------------------------------------------
    # SLM stage
    # -------------------------------------------------------------------
    def _build_prompt(self, chunk_dict: dict, deterministic: List[dict]) -> str:
        template = self.skill.prompt_template
        return template.format(
            language=chunk_dict.get("language", "unknown"),
            chunk_name=chunk_dict.get("name", ""),
            start_line=chunk_dict.get("start_line", 1),
            end_line=chunk_dict.get("end_line", 1),
            code=chunk_dict.get("code", ""),
            deterministic_findings=json.dumps(deterministic, indent=2),
            output_schema=json.dumps(self.skill.output_schema, indent=2),
        )

    def _call_slm(self, model_id: str, prompt: str) -> List[dict]:
        logger.info("    calling SLM '%s' (prompt: %d chars)...", model_id, len(prompt))
        start = time.perf_counter()
        try:
            raw = generate(model_id, prompt, system=self.skill.system_prompt)
        except OllamaError as exc:
            elapsed = time.perf_counter() - start
            logger.warning("    SLM call failed after %.2fs: %s", elapsed, exc)
            return [{
                "severity": "info",
                "line": "1",
                "issue": f"SLM call failed: {exc}",
                "recommendation": "Ensure Ollama is running and the model is pulled.",
                "source": "slm",
            }]

        elapsed = time.perf_counter() - start
        logger.info("    SLM responded in %.2fs (%d chars)", elapsed, len(raw or ""))

        parsed = safe_json_extract(raw)
        if not parsed:
            logger.warning("    SLM returned non-JSON output")
            return [{
                "severity": "info",
                "line": "1",
                "issue": "SLM returned non-JSON output",
                "recommendation": "Inspect the raw response or try a stronger model.",
                "source": "slm",
            }]

        if isinstance(parsed, dict) and isinstance(parsed.get("issues"), list):
            items = parsed["issues"]
        elif isinstance(parsed, list):
            items = parsed
        else:
            items = []

        cleaned: List[dict] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            raw_conf = item.get("confidence")
            try:
                confidence = int(raw_conf) if raw_conf is not None else None
            except (TypeError, ValueError):
                confidence = None
            cleaned.append({
                "severity": str(item.get("severity", "info")).lower(),
                "line": str(item.get("line", "1")),
                "issue": str(item.get("issue", "")),
                "recommendation": str(item.get("recommendation", "")),
                "category": (str(item.get("category")).lower()
                             if item.get("category") else None),
                "confidence": confidence,
                "source": "slm",
            })
        logger.info("    SLM: %d finding(s)", len(cleaned))
        return cleaned

    # -------------------------------------------------------------------
    # SLM sanity-filter stage
    # -------------------------------------------------------------------
    @staticmethod
    def _filter_slm_findings(
        findings: List[dict],
        chunk_start: int,
        chunk_end: int,
        code: str,
        min_confidence: int = 70,
    ) -> Tuple[List[dict], dict]:
        """
        Returns (kept_findings, rejection_stats).
        rejection_stats tracks how many findings each gate dropped.
        """
        kept: List[dict] = []
        stats = {
            "line_range": 0,
            "magic_number": 0,
            "blacklist_phrase": 0,
            "fabricated_quote": 0,
            "unused_var_used": 0,
            "symbol_defined": 0,
            "low_confidence": 0,
        }

        for item in findings:
            issue_text = str(item.get("issue", ""))
            recommendation_text = str(item.get("recommendation", ""))
            combined = issue_text + " " + recommendation_text
            combined_lower = combined.lower()

            # Gate 1: line range
            line_str = str(item.get("line", "")).strip()
            nums = re.findall(r"\d+", line_str)
            if nums:
                line = int(nums[0])
                if not (chunk_start <= line <= chunk_end):
                    stats["line_range"] += 1
                    logger.debug("    SLM reject [line range]: %s", issue_text[:70])
                    continue

            # Gate 2: bogus magic number defaults (0, 1, -1, 0.0, 1.0).
            # Match the *value* the SLM is flagging, not just substrings.
            if "magic number" in combined_lower:
                # Either:
                #   - the value appears in a recognizable shape (e.g. "(0)", "== 1")
                #   - OR the issue explicitly says "literal 0" / "value of 1" etc.
                value_match = re.search(
                    r"(?:literal|value of|value|:|equals?|=)\s*"
                    r"[`'\"]?(-?\d+(?:\.\d+)?)[`'\"]?",
                    combined,
                    re.IGNORECASE,
                )
                bogus = False
                if any(tok in combined for tok in _BOGUS_MAGIC_TOKENS):
                    bogus = True
                elif value_match and value_match.group(1) in _BOGUS_MAGIC_VALUES:
                    bogus = True
                if bogus:
                    stats["magic_number"] += 1
                    logger.debug("    SLM reject [bogus magic]: %s", issue_text[:70])
                    continue

            # Gate 3: blacklisted hallucination phrases
            if any(phrase in combined_lower for phrase in _BAD_PHRASES):
                stats["blacklist_phrase"] += 1
                logger.debug("    SLM reject [blacklist phrase]: %s", issue_text[:70])
                continue

            # Gate 4: "symbol X is not defined" — verify against code
            m = re.search(
                r"[`'\"]?([A-Za-z_][\w.]*)[`'\"]?\s+is\s+not\s+defined",
                issue_text,
                re.IGNORECASE,
            )
            if m:
                symbol = m.group(1).split(".")[0]
                if symbol and re.search(rf"\b{re.escape(symbol)}\b", code):
                    stats["symbol_defined"] += 1
                    logger.debug("    SLM reject [symbol defined]: %s", issue_text[:70])
                    continue

            # Gate 5: unused-variable claim — verify the variable really is unused.
            # Try ALL patterns and collect every candidate name (regex 1 may
            # spuriously capture "is" as the name, regex 2 may capture "db" —
            # if any one of them resolves to a name that's actually used, reject).
            candidate_names = set()
            for pat in _UNUSED_VAR_PATTERNS:
                for m in pat.finditer(combined):
                    name = m.group(1).split(".")[0]
                    if name and name.lower() not in _NAMING_STOPWORDS:
                        candidate_names.add(name)

            if candidate_names:
                rejected = False
                for name in candidate_names:
                    occurrences = _word_occurrences(name, code)
                    is_dep = _is_dependency_param(name, code)
                    if occurrences >= 2 or is_dep:
                        stats["unused_var_used"] += 1
                        logger.debug(
                            "    SLM reject [var '%s' used %d×, dep=%s]: %s",
                            name, occurrences, is_dep, issue_text[:70],
                        )
                        rejected = True
                        break
                if rejected:
                    continue

            # Gate 6: backtick-quoted tokens must appear in the chunk code.
            #         If the SLM quotes ``== False`` but no `== False` exists, reject.
            backticks = _BACKTICK_RE.findall(issue_text)
            if backticks:
                tokens = [t.strip() for t in backticks if len(t.strip()) >= 3]
                if tokens:
                    if not any(t in code for t in tokens):
                        stats["fabricated_quote"] += 1
                        logger.debug(
                            "    SLM reject [fabricated quote: %r]: %s",
                            tokens[0][:30], issue_text[:70],
                        )
                        continue

            # Gate 7: low-confidence rejection
            conf = item.get("confidence")
            if isinstance(conf, int) and conf < min_confidence:
                stats["low_confidence"] += 1
                logger.debug(
                    "    SLM reject [confidence %d<%d]: %s",
                    conf, min_confidence, issue_text[:70],
                )
                continue

            kept.append(item)

        return kept, stats

    # -------------------------------------------------------------------
    # Merge stage — fuzzy de-duplication with ±3-line tolerance
    # -------------------------------------------------------------------
    @staticmethod
    def _merge(deterministic: List[dict], slm: List[dict]) -> List[dict]:
        """
        De-duplicate with proximity awareness. Two findings are considered
        the same if they share severity + normalized issue text AND their
        line numbers are within 10 lines of each other. Bucketed fingerprints
        miss boundary cases (e.g. lines 197 and 201 with the same issue);
        the explicit proximity check catches them.
        """

        def normalize(text: str) -> str:
            text = re.sub(r"\([^)]*\)", "", text.lower())
            text = re.sub(r"\d+(?:\.\d+)?", "", text)
            text = re.sub(r"[`'\"]+", "", text)
            return re.sub(r"\s+", " ", text).strip()[:60]

        def parse_line(item: dict) -> int:
            nums = re.findall(r"\d+", str(item.get("line", "")))
            return int(nums[0]) if nums else 0

        merged: List[dict] = []
        for src in (deterministic, slm):
            for item in src:
                norm = normalize(item.get("issue", ""))
                sev = str(item.get("severity", "")).lower()
                line = parse_line(item)

                is_dup = False
                for existing in merged:
                    if normalize(existing.get("issue", "")) != norm:
                        continue
                    if str(existing.get("severity", "")).lower() != sev:
                        continue
                    if abs(parse_line(existing) - line) > 10:
                        continue
                    is_dup = True
                    break

                if not is_dup:
                    merged.append(item)
        return merged

    # -------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------
    def review_chunk(
        self,
        chunk: CodeChunk,
        model_id: str,
        file_name: str,
        chunking_strategy: str,
    ) -> dict:
        chunk_start_time = time.perf_counter()
        chunk_dict = asdict(chunk)
        deterministic = self._run_deterministic(chunk_dict)
        prompt = self._build_prompt(chunk_dict, deterministic)
        slm_findings = self._call_slm(model_id, prompt)
        raw_slm_count = len(slm_findings)

        slm_findings, reject_stats = self._filter_slm_findings(
            slm_findings, chunk.start_line, chunk.end_line, chunk.code,
        )
        rejected_total = raw_slm_count - len(slm_findings)
        if rejected_total > 0:
            reject_summary = ", ".join(f"{k}={v}" for k, v in reject_stats.items() if v)
            logger.info(
                "    sanity filter dropped %d SLM finding(s) [%s]",
                rejected_total, reject_summary,
            )

        issues = self._merge(deterministic, slm_findings)
        logger.info(
            "    merged: %d total (chunk took %.2fs)",
            len(issues),
            time.perf_counter() - chunk_start_time,
        )

        return {
            "file_name": file_name,
            "chunk_id": chunk.chunk_id,
            "chunk_type": chunk.chunk_type,
            "language": chunk.language,
            "start_line": chunk.start_line,
            "end_line": chunk.end_line,
            "code": chunk.code,
            "model": model_id,
            "chunking_strategy": chunking_strategy,
            "skill": self.skill.name,
            "issues": issues,
        }

    # -------------------------------------------------------------------
    # Scoring stage — runs once after every chunk has been reviewed.
    # Generic at the agent level: each skill ships its own scoring.py.
    # -------------------------------------------------------------------
    def compute_scoring(self, results: List[dict]):
        if not self.skill.scoring:
            logger.info("    no scoring.py for skill '%s' — skipping", self.skill.name)
            return None
        try:
            scoring = self.skill.scoring(results, self.skill.resources)
            overall = scoring.get("overall", {}) if isinstance(scoring, dict) else {}
            logger.info(
                "    scoring: overall %.1f (%s) across %d aspect(s)",
                overall.get("score", 0),
                overall.get("grade", "?"),
                len(scoring.get("aspects", [])) if isinstance(scoring, dict) else 0,
            )
            return scoring
        except Exception as exc:
            logger.warning("    scoring failed for skill '%s': %s", self.skill.name, exc)
            return None

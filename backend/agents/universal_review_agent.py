"""
Universal Review Agent
======================
A SINGLE agent (not multi-agent) that:

1. Loads a skill dynamically by name.
2. Runs every deterministic script in that skill against a chunk.
3. Builds a prompt from the skill's prompt template + deterministic findings.
4. Calls the active SLM via Ollama.
5. Merges deterministic + SLM findings into the final structured output.

The agent itself has NO hardcoded knowledge of static review, security
review, etc. — all rules live inside the skill folder.
"""

import json
import logging
import re
import time
from dataclasses import asdict
from typing import List

from chunking.base import CodeChunk
from llm.ollama_client import OllamaError, generate, safe_json_extract
from skill_loader.loader import LoadedSkill, load_skill

logger = logging.getLogger("ura.agent")

# Common defaults the SLM tends to flag as "magic numbers" — they aren't.
_BOGUS_MAGIC_TOKENS = ("0.0", "1.0", "-1.0", "(0)", "(1)", "(-1)", "== 0", "== 1")


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
                # A broken script must not crash the pipeline.
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
        logger.info(
            "    SLM responded in %.2fs (%d chars)", elapsed, len(raw or "")
        )

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

        # The schema we ask for is {"issues": [...]} — accept a bare list too.
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
            cleaned.append({
                "severity": str(item.get("severity", "info")).lower(),
                "line": str(item.get("line", "1")),
                "issue": str(item.get("issue", "")),
                "recommendation": str(item.get("recommendation", "")),
                "source": "slm",
            })
        logger.info("    SLM: %d finding(s)", len(cleaned))
        return cleaned

    # -------------------------------------------------------------------
    # Sanity-filter stage (applied only to SLM output)
    # -------------------------------------------------------------------
    @staticmethod
    def _filter_slm_findings(
        findings: List[dict], chunk_start: int, chunk_end: int, code: str
    ) -> List[dict]:
        """
        Drop SLM findings that fail basic sanity checks:
        - Line number outside the chunk's [start_line, end_line] range
        - "Magic number" complaints about common defaults (0, 1, -1, 0.0, 1.0)
        - "Symbol X is not defined" when X actually appears in the chunk's code
        """
        kept: List[dict] = []
        for item in findings:
            line_str = str(item.get("line", "")).strip()
            nums = re.findall(r"\d+", line_str)
            if nums:
                line = int(nums[0])
                if not (chunk_start <= line <= chunk_end):
                    logger.debug(
                        "    SLM reject (line %d out of %d-%d): %s",
                        line, chunk_start, chunk_end,
                        str(item.get("issue", ""))[:70],
                    )
                    continue

            issue_text = str(item.get("issue", ""))
            issue_lower = issue_text.lower()

            if "magic number" in issue_lower and any(
                tok in issue_text for tok in _BOGUS_MAGIC_TOKENS
            ):
                logger.debug(
                    "    SLM reject (bogus magic number): %s", issue_text[:70]
                )
                continue

            # "X is not defined" hallucination — check if the symbol appears in code.
            m = re.search(
                r"[`'\"]?([A-Za-z_][\w\.]*)[`'\"]?\s+is\s+not\s+defined",
                issue_text,
                re.IGNORECASE,
            )
            if m:
                symbol = m.group(1).split(".")[0]
                if symbol and re.search(rf"\b{re.escape(symbol)}\b", code):
                    logger.debug(
                        "    SLM reject (symbol '%s' actually defined): %s",
                        symbol, issue_text[:70],
                    )
                    continue

            kept.append(item)
        return kept

    # -------------------------------------------------------------------
    # Merge stage (fuzzy de-duplication)
    # -------------------------------------------------------------------
    @staticmethod
    def _merge(deterministic: List[dict], slm: List[dict]) -> List[dict]:
        """
        De-duplicate while preserving order. Dedup key normalizes whitespace
        and truncates at 80 chars so two near-identical findings collapse.
        """
        def normalize(text: str) -> str:
            return re.sub(r"\s+", " ", text.lower()).strip()[:80]

        seen = set()
        merged: List[dict] = []
        for src in (deterministic, slm):
            for item in src:
                key = (str(item.get("line", "")), normalize(item.get("issue", "")))
                if key in seen:
                    continue
                seen.add(key)
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
        chunk_start = time.perf_counter()
        chunk_dict = asdict(chunk)
        deterministic = self._run_deterministic(chunk_dict)
        prompt = self._build_prompt(chunk_dict, deterministic)
        slm_findings = self._call_slm(model_id, prompt)
        raw_slm_count = len(slm_findings)
        slm_findings = self._filter_slm_findings(
            slm_findings, chunk.start_line, chunk.end_line, chunk.code
        )
        rejected = raw_slm_count - len(slm_findings)
        if rejected > 0:
            logger.info("    sanity filter dropped %d SLM finding(s)", rejected)
        issues = self._merge(deterministic, slm_findings)
        logger.info(
            "    merged: %d total (chunk took %.2fs)",
            len(issues),
            time.perf_counter() - chunk_start,
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

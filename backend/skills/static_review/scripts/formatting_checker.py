"""
formatting_checker
==================
Lightweight PEP8-style formatting checks. Designed to be language-agnostic
where possible (line length, tabs, trailing whitespace, etc.).
"""

from typing import List


def _finding(severity: str, line: int, issue: str, recommendation: str) -> dict:
    return {
        "severity": severity,
        "line": str(line),
        "issue": issue,
        "recommendation": recommendation,
    }


def run(chunk: dict, resources: dict) -> List[dict]:
    pep8 = resources.get("pep8_rules", {})
    max_len = int(pep8.get("max_line_length", 100))
    tabs_allowed = bool(pep8.get("tabs_allowed", False))
    trailing_ws_allowed = bool(pep8.get("trailing_whitespace", False))

    out: List[dict] = []
    code = chunk.get("code", "")
    start_line = int(chunk.get("start_line", 1))

    for i, raw_line in enumerate(code.splitlines()):
        absolute_line = start_line + i

        if len(raw_line) > max_len:
            out.append(_finding(
                "low", absolute_line,
                f"Line exceeds {max_len} characters ({len(raw_line)})",
                "Wrap or refactor to keep lines under the limit",
            ))

        if not tabs_allowed and "\t" in raw_line:
            out.append(_finding(
                "low", absolute_line,
                "Tab character used for indentation",
                "Use spaces instead of tabs",
            ))

        if not trailing_ws_allowed and raw_line != raw_line.rstrip():
            out.append(_finding(
                "info", absolute_line,
                "Trailing whitespace",
                "Strip trailing whitespace",
            ))

    # Cheap "double blank line at top of function" style smell: more than 2
    # consecutive blank lines is almost always unintentional inside a chunk.
    blank_streak = 0
    for i, raw_line in enumerate(code.splitlines()):
        if raw_line.strip() == "":
            blank_streak += 1
            if blank_streak == 3:
                out.append(_finding(
                    "info", start_line + i,
                    "Three or more consecutive blank lines",
                    "Collapse to at most two blank lines",
                ))
        else:
            blank_streak = 0

    return out

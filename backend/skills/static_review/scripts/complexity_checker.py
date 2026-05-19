"""
complexity_checker
==================
Calculates a lightweight cyclomatic-complexity proxy and deep-nesting depth
for the chunk. Flags chunks that exceed the PEP8-rules thresholds.
"""

import ast
import io
import re
import tokenize
from typing import List

_BRANCH_NODES = (
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.Try,
    ast.With,
    ast.AsyncWith,
    ast.BoolOp,
    ast.IfExp,
)


def _nesting_depth_python(node: ast.AST, current: int = 0) -> int:
    deepest = current
    for child in ast.iter_child_nodes(node):
        if isinstance(child, _BRANCH_NODES):
            deepest = max(deepest, _nesting_depth_python(child, current + 1))
        else:
            deepest = max(deepest, _nesting_depth_python(child, current))
    return deepest


def _cyclomatic_python(node: ast.AST) -> int:
    score = 1
    for sub in ast.walk(node):
        if isinstance(sub, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler)):
            score += 1
        elif isinstance(sub, ast.BoolOp):
            score += max(0, len(sub.values) - 1)
    return score


def _nesting_depth_generic(code: str) -> int:
    """Count maximum brace nesting for non-Python code."""
    depth = 0
    max_depth = 0
    for ch in code:
        if ch == "{":
            depth += 1
            max_depth = max(max_depth, depth)
        elif ch == "}":
            depth = max(0, depth - 1)
    return max_depth


def _cyclomatic_generic(code: str) -> int:
    keywords = re.findall(r"\b(if|else if|elif|for|while|case|catch|&&|\|\|)\b", code)
    return 1 + len(keywords)


def _effective_line_count(code: str, language: str) -> int:
    """
    Count "real" code lines, excluding:
    - Blank lines
    - Comment-only lines
    - Standalone docstring/string-statement lines

    For Python we use `tokenize` for accuracy. For other languages we fall
    back to a simple heuristic (blank + `//` / `#` comment skipping).
    """
    if language == "python":
        try:
            return _effective_lines_python(code)
        except Exception:
            pass

    count = 0
    in_block_comment = False
    for raw in code.splitlines():
        stripped = raw.strip()
        if not stripped:
            continue
        # Very rough multi-line comment handling for C-like langs.
        if in_block_comment:
            if "*/" in stripped:
                in_block_comment = False
            continue
        if stripped.startswith("/*"):
            if "*/" not in stripped[2:]:
                in_block_comment = True
            continue
        if stripped.startswith(("#", "//")):
            continue
        count += 1
    return count


def _effective_lines_python(code: str) -> int:
    """
    Python-specific: count lines that contain at least one token that is
    NOT a comment, NL, NEWLINE, INDENT, DEDENT, ENCODING, ENDMARKER,
    or a standalone string-statement (docstring).
    """
    significant_lines: set[int] = set()
    string_only_lines: set[int] = set()
    other_token_lines: set[int] = set()
    skip_types = {
        tokenize.COMMENT,
        tokenize.NL,
        tokenize.NEWLINE,
        tokenize.INDENT,
        tokenize.DEDENT,
        tokenize.ENCODING,
        tokenize.ENDMARKER,
    }
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(code).readline))
    except (tokenize.TokenizeError, IndentationError):
        # Fall back to raw line count if tokenization fails.
        return len([l for l in code.splitlines() if l.strip()])

    for tok in tokens:
        if tok.type in skip_types:
            continue
        start_row = tok.start[0]
        end_row = tok.end[0]
        if tok.type == tokenize.STRING:
            for row in range(start_row, end_row + 1):
                string_only_lines.add(row)
        else:
            for row in range(start_row, end_row + 1):
                other_token_lines.add(row)

    # A line with both STRING and other tokens is "real code" (e.g. `x = "hi"`).
    # A line with ONLY STRING tokens is likely a docstring — exclude it.
    significant_lines = other_token_lines | (
        # strings paired with non-strings on same line are already in other_token_lines;
        # nothing else to add.
        set()
    )
    return len(significant_lines)


def _finding(severity: str, line: int, issue: str, recommendation: str) -> dict:
    return {
        "severity": severity,
        "line": str(line),
        "issue": issue,
        "recommendation": recommendation,
    }


def run(chunk: dict, resources: dict) -> List[dict]:
    pep8 = resources.get("pep8_rules", {})
    max_nesting = int(pep8.get("max_nesting_depth", 4))
    max_lines = int(pep8.get("max_function_lines", 50))

    code = chunk.get("code", "")
    language = chunk.get("language", "unknown")
    start_line = int(chunk.get("start_line", 1))
    end_line = int(chunk.get("end_line", start_line))
    chunk_lines = max(1, end_line - start_line + 1)
    effective_lines = _effective_line_count(code, language) or chunk_lines

    out: List[dict] = []

    if language == "python":
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return out
        depth = _nesting_depth_python(tree)
        complexity = _cyclomatic_python(tree)
    else:
        depth = _nesting_depth_generic(code)
        complexity = _cyclomatic_generic(code)

    if depth > max_nesting:
        out.append(_finding(
            "high", start_line,
            f"Deep nesting detected (depth={depth}, max allowed={max_nesting})",
            "Refactor by extracting helper functions or using early returns",
        ))

    if complexity > 10:
        severity = "high" if complexity > 15 else "medium"
        out.append(_finding(
            severity, start_line,
            f"High cyclomatic complexity (~{complexity})",
            "Split this function into smaller, single-purpose helpers",
        ))

    # Use "effective" line count (excluding blanks, comments, docstrings) so
    # well-documented but reasonably-sized functions aren't penalized.
    if effective_lines > max_lines:
        out.append(_finding(
            "medium", start_line,
            (f"Function is too long ({effective_lines} effective lines, "
             f"{chunk_lines} total, max {max_lines})"),
            "Break this function into smaller cohesive pieces",
        ))

    return out

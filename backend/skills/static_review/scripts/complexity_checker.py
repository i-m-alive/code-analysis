"""
complexity_checker
==================
Calculates a lightweight cyclomatic-complexity proxy and deep-nesting depth
for the chunk. Flags chunks that exceed the PEP8-rules thresholds.
"""

import ast
import re
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

    if chunk_lines > max_lines:
        out.append(_finding(
            "medium", start_line,
            f"Function is too long ({chunk_lines} lines, max {max_lines})",
            "Break this function into smaller cohesive pieces",
        ))

    return out

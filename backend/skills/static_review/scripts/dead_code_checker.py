"""
dead_code_checker
=================
Detects obvious dead code patterns:
- Unreachable statements after `return`, `raise`, `break`, `continue`
- `if False:` / `while False:` blocks
- Empty exception handlers that swallow errors (a code smell, flagged as info)
"""

import ast
from typing import List


def _finding(severity: str, line: int, issue: str, recommendation: str) -> dict:
    return {
        "severity": severity,
        "line": str(line),
        "issue": issue,
        "recommendation": recommendation,
    }


def _walk_block(body: list, start_line: int, out: List[dict]) -> None:
    terminated = False
    for stmt in body:
        line = start_line + getattr(stmt, "lineno", 1) - 1
        if terminated:
            out.append(_finding(
                "medium", line,
                "Unreachable code after return/raise/break/continue",
                "Remove the unreachable statements",
            ))
            terminated = False  # only flag the first one per block
        if isinstance(stmt, (ast.Return, ast.Raise, ast.Break, ast.Continue)):
            terminated = True
        # Recurse into nested blocks.
        for attr in ("body", "orelse", "finalbody"):
            inner = getattr(stmt, attr, None)
            if isinstance(inner, list):
                _walk_block(inner, start_line, out)


def run(chunk: dict, resources: dict) -> List[dict]:
    if chunk.get("language") != "python":
        return []

    out: List[dict] = []
    try:
        tree = ast.parse(chunk.get("code", ""))
    except SyntaxError:
        return out

    start_line = int(chunk.get("start_line", 1))

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Module)):
            _walk_block(getattr(node, "body", []), start_line, out)
        if isinstance(node, ast.If):
            test = node.test
            if isinstance(test, ast.Constant) and test.value is False:
                line = start_line + node.lineno - 1
                out.append(_finding(
                    "medium", line,
                    "`if False:` block is dead code",
                    "Remove the block or replace with a feature flag",
                ))
        if isinstance(node, ast.While):
            test = node.test
            if isinstance(test, ast.Constant) and test.value is False:
                line = start_line + node.lineno - 1
                out.append(_finding(
                    "medium", line,
                    "`while False:` loop is dead code",
                    "Remove the loop",
                ))
        if isinstance(node, ast.ExceptHandler):
            # A `pass`-only handler silently swallows errors. We intentionally
            # only flag NARROW excepts here — broad `except Exception:` /
            # bare `except:` are owned by code_smell_checker (at higher
            # severity), and we don't want to double-flag the same line.
            is_broad = (
                node.type is None
                or (
                    isinstance(node.type, ast.Name)
                    and node.type.id in ("Exception", "BaseException")
                )
            )
            if not is_broad and len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                line = start_line + node.lineno - 1
                out.append(_finding(
                    "info", line,
                    "Empty except handler silently swallows errors",
                    "At minimum log the exception",
                ))
    return out

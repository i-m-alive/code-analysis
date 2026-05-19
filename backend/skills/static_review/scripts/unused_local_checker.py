"""
unused_local_checker
====================
AST-based detection of local variables that are assigned inside a function
body but never read elsewhere in the same scope.

Skips:
- Names starting with `_` (Python convention for intentionally unused)
- Names listed in resources/naming_rules.json `allowed_short_names`
- Function parameters (those have their own checks; FastAPI's `Depends(...)`
  arguments have side effects)
- Tuple-unpacking targets where any element is referenced

By emitting REAL unused-variable findings deterministically, we give the
SLM-sanity-gate a comparison source — when the SLM later claims "X is
unused", we can cross-check against this checker's output.
"""

import ast
from typing import List, Set


def _finding(severity: str, line: int, issue: str, recommendation: str,
             category: str = "maintainability") -> dict:
    return {
        "severity": severity,
        "line": str(line),
        "issue": issue,
        "recommendation": recommendation,
        "category": category,
    }


def _names_read(scope_node: ast.AST) -> Set[str]:
    """Return every name read (Load context) anywhere in the scope."""
    names: Set[str] = set()
    for node in ast.walk(scope_node):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            names.add(node.id)
        elif isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name):
            # `x += 1` reads then writes — count target as read.
            names.add(node.target.id)
        elif isinstance(node, ast.Attribute):
            # Walk attribute chains to the root Name (e.g. `db.query.filter` → `db`).
            cur = node
            while isinstance(cur, ast.Attribute):
                cur = cur.value
            if isinstance(cur, ast.Name) and isinstance(cur.ctx, ast.Load):
                names.add(cur.id)
        elif isinstance(node, ast.FormattedValue):
            # f-string variable references.
            if isinstance(node.value, ast.Name):
                names.add(node.value.id)
    return names


def _collect_params(func_node: ast.AST) -> Set[str]:
    params: Set[str] = set()
    args = func_node.args
    for arg in args.args + args.kwonlyargs:
        params.add(arg.arg)
    if args.vararg:
        params.add(args.vararg.arg)
    if args.kwarg:
        params.add(args.kwarg.arg)
    return params


def run(chunk: dict, resources: dict) -> List[dict]:
    if chunk.get("language") != "python":
        return []

    code = chunk.get("code", "")
    start_line = int(chunk.get("start_line", 1))

    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []

    naming_rules = resources.get("naming_rules", {}).get("python", {})
    allowed_short: Set[str] = set(naming_rules.get("allowed_short_names", []))

    findings: List[dict] = []

    for func_node in ast.walk(tree):
        if not isinstance(func_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        used = _names_read(func_node)
        params = _collect_params(func_node)

        # Track assignments seen so we only flag the first occurrence per name.
        flagged: Set[str] = set()

        for stmt in ast.walk(func_node):
            if not isinstance(stmt, ast.Assign):
                continue
            for target in stmt.targets:
                # Only simple `name = ...` — skip subscript / attribute / tuple
                # targets (those have separate semantics).
                if not isinstance(target, ast.Name):
                    continue
                name = target.id
                if name in flagged:
                    continue
                if name.startswith("_"):
                    continue
                if name in allowed_short:
                    continue
                if name in params:
                    continue
                if name in used:
                    continue

                abs_line = start_line + stmt.lineno - 1
                findings.append(_finding(
                    "low", abs_line,
                    f"Local variable `{name}` is assigned but never read",
                    f"Remove the assignment, or rename to `_` if intentional.",
                ))
                flagged.add(name)

    return findings

"""
unused_import_checker
=====================
Detects imports that are not referenced anywhere else in the chunk.

NOTE: chunks usually contain a single function and rarely contain imports,
so this check is most useful when the chunker falls back to whole-file mode.
"""

import ast
from typing import List, Set


def _finding(severity: str, line: int, issue: str, recommendation: str) -> dict:
    return {
        "severity": severity,
        "line": str(line),
        "issue": issue,
        "recommendation": recommendation,
    }


def run(chunk: dict, resources: dict) -> List[dict]:
    if chunk.get("language") != "python":
        return []

    code = chunk.get("code", "")
    start_line = int(chunk.get("start_line", 1))

    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []

    imported: dict[str, int] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.asname or alias.name.split(".")[0]
                imported[name] = node.lineno
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "*":
                    continue
                name = alias.asname or alias.name
                imported[name] = node.lineno

    if not imported:
        return []

    used: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            used.add(node.id)
        elif isinstance(node, ast.Attribute):
            cur = node
            while isinstance(cur, ast.Attribute):
                cur = cur.value
            if isinstance(cur, ast.Name):
                used.add(cur.id)

    out: List[dict] = []
    for name, line in imported.items():
        if name not in used:
            out.append(_finding(
                "low", start_line + line - 1,
                f"Unused import '{name}'",
                f"Remove `{name}` if it is not needed",
            ))
    return out

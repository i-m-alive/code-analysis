"""
naming_checker
==============
Validates identifier naming against rules in resources/naming_rules.json.

Improvements over the v1 checker:
- Names bound by `for x in ...` or list/dict/set/generator comprehensions are
  NOT flagged for length — short loop vars are idiomatic Python.
- Identifiers listed in `allowed_short_names` bypass the min-length rule.
"""

import ast
import re
from typing import List, Set


def _check_python(code: str, start_line: int, rules: dict) -> List[dict]:
    out: List[dict] = []
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return out

    fn_re = re.compile(rules.get("function", "^[a-z_][a-z0-9_]*$"))
    cls_re = re.compile(rules.get("class", "^[A-Z][A-Za-z0-9]*$"))
    var_re = re.compile(rules.get("variable", "^[a-z_][a-z0-9_]*$"))
    const_re = re.compile(rules.get("constant", "^[A-Z][A-Z0-9_]*$"))
    min_len = int(rules.get("min_identifier_length", 2))
    forbidden = set(rules.get("forbidden_names", []))
    allowed_short: Set[str] = set(rules.get("allowed_short_names", []))

    # Pre-collect identifiers bound by for-loops / comprehensions so we can
    # exempt them from the length check.
    loop_targets: Set[str] = _collect_loop_targets(tree)

    def absolute_line(node) -> int:
        return start_line + getattr(node, "lineno", 1) - 1

    def length_exempt(name: str) -> bool:
        return name in allowed_short or name in loop_targets or name == "_"

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            name = node.name
            if not fn_re.match(name):
                out.append(_finding("medium", absolute_line(node),
                    f"Function name '{name}' violates naming convention",
                    f"Rename to snake_case matching {rules.get('function')}",
                    category="style"))
            if name in forbidden:
                out.append(_finding("low", absolute_line(node),
                    f"Function uses placeholder name '{name}'",
                    "Use a descriptive name reflecting the function's purpose",
                    category="style"))
        elif isinstance(node, ast.ClassDef):
            if not cls_re.match(node.name):
                out.append(_finding("medium", absolute_line(node),
                    f"Class name '{node.name}' violates PascalCase",
                    f"Rename to PascalCase matching {rules.get('class')}",
                    category="style"))
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    name = target.id
                    if len(name) < min_len and not length_exempt(name):
                        out.append(_finding("low", absolute_line(node),
                            f"Identifier '{name}' is too short",
                            f"Use at least {min_len} characters and a meaningful name",
                            category="style"))
                    if name in forbidden:
                        out.append(_finding("low", absolute_line(node),
                            f"Variable uses placeholder name '{name}'",
                            "Use a descriptive name",
                            category="style"))
                    if name.isupper():
                        if not const_re.match(name):
                            out.append(_finding("low", absolute_line(node),
                                f"Constant '{name}' violates UPPER_SNAKE_CASE",
                                "Rename to UPPER_SNAKE_CASE",
                                category="style"))
                    elif not var_re.match(name) and not length_exempt(name):
                        out.append(_finding("low", absolute_line(node),
                            f"Variable '{name}' violates snake_case",
                            "Rename to snake_case",
                            category="style"))
    return out


def _collect_loop_targets(tree: ast.AST) -> Set[str]:
    """Return the set of names bound by for-loops and comprehensions."""
    targets: Set[str] = set()

    def add_from(target):
        if isinstance(target, ast.Name):
            targets.add(target.id)
        elif isinstance(target, (ast.Tuple, ast.List)):
            for elt in target.elts:
                add_from(elt)

    for node in ast.walk(tree):
        if isinstance(node, (ast.For, ast.AsyncFor)):
            add_from(node.target)
        if isinstance(node, ast.comprehension):
            add_from(node.target)
    return targets


def _check_generic(code: str, start_line: int, rules: dict) -> List[dict]:
    out: List[dict] = []
    if not rules:
        return out
    fn_re = re.compile(r"\bfunction\s+([A-Za-z_$][\w$]*)\s*\(")
    forbidden = set(rules.get("forbidden_names", []))
    for m in fn_re.finditer(code):
        name = m.group(1)
        line = start_line + code.count("\n", 0, m.start())
        if name in forbidden:
            out.append(_finding("low", line,
                f"Function uses placeholder name '{name}'",
                "Use a descriptive name", category="style"))
    return out


def _finding(severity: str, line: int, issue: str, recommendation: str,
             category: str = "style") -> dict:
    return {
        "severity": severity,
        "line": str(line),
        "issue": issue,
        "recommendation": recommendation,
        "category": category,
    }


def run(chunk: dict, resources: dict) -> List[dict]:
    naming_rules = resources.get("naming_rules", {})
    language = chunk.get("language", "unknown")
    rules = naming_rules.get(language, {})
    if not rules:
        return []
    code = chunk.get("code", "")
    start_line = int(chunk.get("start_line", 1))
    if language == "python":
        return _check_python(code, start_line, rules)
    return _check_generic(code, start_line, rules)

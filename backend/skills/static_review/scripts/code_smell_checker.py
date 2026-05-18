"""
code_smell_checker
==================
High-signal Python smells the SLM tends to miss:

- print() outside `if __name__ == "__main__":`
- `== True` / `== False` / `== None`         (use `is`)
- `except Exception:` / bare `except:`       without logging or re-raise
- imports inside function bodies             (smell, not always wrong)
- functions exceeding `max_parameters`

All findings include a `category` so the dashboard can slice by type.
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


def _is_main_guard(node: ast.AST) -> bool:
    """Detect `if __name__ == "__main__":` so prints inside are tolerated."""
    if not isinstance(node, ast.If):
        return False
    test = node.test
    if not isinstance(test, ast.Compare):
        return False
    left = test.left
    if not isinstance(left, ast.Name) or left.id != "__name__":
        return False
    if not test.comparators:
        return False
    cmp = test.comparators[0]
    return isinstance(cmp, ast.Constant) and cmp.value == "__main__"


def _collect_main_guard_lines(tree: ast.AST) -> Set[int]:
    lines: Set[int] = set()
    for node in ast.walk(tree):
        if _is_main_guard(node):
            for inner in ast.walk(node):
                if hasattr(inner, "lineno"):
                    lines.add(inner.lineno)
    return lines


def _has_log_or_reraise(handler: ast.ExceptHandler) -> bool:
    log_methods = {"error", "exception", "warning", "critical", "warn", "info", "debug"}
    for inner in ast.walk(handler):
        if isinstance(inner, ast.Raise):
            return True
        if isinstance(inner, ast.Call):
            func = inner.func
            if isinstance(func, ast.Attribute) and func.attr in log_methods:
                return True
            if isinstance(func, ast.Name) and func.id == "print":
                # `print` in an except is poor but at least surfaces the error.
                return True
    return False


def _count_params(node) -> int:
    args = node.args
    count = (
        len(args.args)
        + len(args.kwonlyargs)
        + (1 if args.vararg else 0)
        + (1 if args.kwarg else 0)
    )
    # Don't count `self` / `cls`.
    if args.args and args.args[0].arg in ("self", "cls"):
        count -= 1
    return count


def run(chunk: dict, resources: dict) -> List[dict]:
    if chunk.get("language") != "python":
        return []

    code = chunk.get("code", "")
    start_line = int(chunk.get("start_line", 1))
    pep8 = resources.get("pep8_rules", {})
    max_params = int(pep8.get("max_parameters", 5))

    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []

    def absolute(node) -> int:
        return start_line + getattr(node, "lineno", 1) - 1

    findings: List[dict] = []
    main_guard_lines = _collect_main_guard_lines(tree)

    for node in ast.walk(tree):
        # print() outside __main__ guard
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "print"
            and node.lineno not in main_guard_lines
        ):
            findings.append(_finding(
                "low", absolute(node),
                "`print()` used outside a __main__ guard",
                "Use a structured logger (logging.getLogger(__name__).info(...)).",
                category="maintainability",
            ))

        # == True / == False / == None
        if isinstance(node, ast.Compare):
            for op, cmp in zip(node.ops, node.comparators):
                if not isinstance(op, ast.Eq):
                    continue
                if isinstance(cmp, ast.Constant) and cmp.value in (True, False, None):
                    target = (
                        "True" if cmp.value is True
                        else "False" if cmp.value is False
                        else "None"
                    )
                    findings.append(_finding(
                        "low", absolute(node),
                        f"Comparison `== {target}` should use `is {target}`",
                        f"Replace `== {target}` with `is {target}` (also: SQLAlchemy uses `.is_(...)`).",
                        category="correctness",
                    ))

        # Broad except without log or re-raise
        if isinstance(node, ast.ExceptHandler):
            is_broad = (
                node.type is None
                or (isinstance(node.type, ast.Name)
                    and node.type.id in ("Exception", "BaseException"))
            )
            if is_broad and not _has_log_or_reraise(node):
                findings.append(_finding(
                    "medium", absolute(node),
                    "Broad `except` block neither logs nor re-raises",
                    "Catch a specific exception, or log via `logger.exception(...)` and/or re-raise.",
                    category="correctness",
                ))

        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Imports inside function bodies
            for inner in node.body:
                if isinstance(inner, (ast.Import, ast.ImportFrom)):
                    mod = (
                        inner.module
                        if isinstance(inner, ast.ImportFrom)
                        else (inner.names[0].name if inner.names else "")
                    )
                    findings.append(_finding(
                        "low", absolute(inner),
                        f"Import of `{mod}` inside function `{node.name}`",
                        "Move imports to the top of the module unless avoiding circular imports.",
                        category="maintainability",
                    ))

            # Too many parameters
            num_params = _count_params(node)
            if num_params > max_params:
                findings.append(_finding(
                    "medium", absolute(node),
                    f"Function `{node.name}` has {num_params} parameters (max {max_params})",
                    "Group related parameters into a dataclass or config object.",
                    category="maintainability",
                ))

    return findings

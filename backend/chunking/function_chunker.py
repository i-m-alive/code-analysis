"""
Function-level chunker.

For Python we use the AST for accuracy (handles decorators, nested defs).
For other supported languages we fall back to a lightweight regex heuristic,
which is good enough for an experimentation harness.

If no functions can be detected, the whole file is returned as a single
"module" chunk so the SLM still has something to look at.
"""

import ast
import re
from typing import List

from chunking.base import BaseChunker, CodeChunk

# Heuristic patterns for function-like declarations in non-Python sources.
# Intentionally permissive — we'd rather over-capture than miss functions.
_NON_PY_FUNCTION_PATTERNS = {
    "javascript": [
        re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(", re.MULTILINE),
        re.compile(r"^\s*(?:export\s+)?const\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\(.*?\)\s*=>", re.MULTILINE),
    ],
    "typescript": [
        re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(", re.MULTILINE),
        re.compile(r"^\s*(?:export\s+)?const\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\(.*?\)\s*=>", re.MULTILINE),
    ],
    "java": [
        re.compile(r"^\s*(?:public|protected|private|static|\s)+[\w<>\[\]]+\s+([\w]+)\s*\([^)]*\)\s*(?:throws[\w\s,]+)?\s*\{", re.MULTILINE),
    ],
    "go": [
        re.compile(r"^\s*func\s+(?:\([^)]+\)\s+)?([A-Za-z_]\w*)\s*\(", re.MULTILINE),
    ],
    "csharp": [
        re.compile(r"^\s*(?:public|private|protected|internal|static|\s)+[\w<>\[\]]+\s+([\w]+)\s*\([^)]*\)\s*\{", re.MULTILINE),
    ],
}


class FunctionChunker(BaseChunker):
    strategy_id = "function"

    def chunk(self, source: str, language: str, file_name: str) -> List[CodeChunk]:
        if language == "python":
            chunks = self._chunk_python(source, file_name)
        else:
            chunks = self._chunk_regex(source, language, file_name)

        if not chunks:
            # Fallback so downstream code always has something to review.
            lines = source.splitlines()
            chunks = [
                CodeChunk(
                    chunk_id=f"{file_name}::module",
                    chunk_type="function",
                    name="<module>",
                    start_line=1,
                    end_line=max(1, len(lines)),
                    code=source,
                    language=language,
                    metadata={"fallback": True},
                )
            ]
        return chunks

    def _chunk_python(self, source: str, file_name: str) -> List[CodeChunk]:
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return []

        lines = source.splitlines()
        out: List[CodeChunk] = []

        def add_node(node, qualifier: str = ""):
            start = getattr(node, "lineno", 1)
            end = getattr(node, "end_lineno", start)
            code = "\n".join(lines[start - 1 : end])
            name = f"{qualifier}{node.name}" if qualifier else node.name
            out.append(
                CodeChunk(
                    chunk_id=f"{file_name}::{name}#{start}",
                    chunk_type="function",
                    name=name,
                    start_line=start,
                    end_line=end,
                    code=code,
                    language="python",
                    metadata={"is_async": isinstance(node, ast.AsyncFunctionDef)},
                )
            )

        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                add_node(node)
            elif isinstance(node, ast.ClassDef):
                for sub in node.body:
                    if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        add_node(sub, qualifier=f"{node.name}.")
        return out

    def _chunk_regex(self, source: str, language: str, file_name: str) -> List[CodeChunk]:
        patterns = _NON_PY_FUNCTION_PATTERNS.get(language)
        if not patterns:
            return []

        lines = source.splitlines()
        matches = []
        for pattern in patterns:
            for m in pattern.finditer(source):
                start_idx = m.start()
                # Convert char offset to line number.
                start_line = source.count("\n", 0, start_idx) + 1
                matches.append((start_line, m.group(1)))

        if not matches:
            return []

        matches.sort()
        out: List[CodeChunk] = []
        for i, (start_line, name) in enumerate(matches):
            end_line = matches[i + 1][0] - 1 if i + 1 < len(matches) else len(lines)
            code = "\n".join(lines[start_line - 1 : end_line])
            out.append(
                CodeChunk(
                    chunk_id=f"{file_name}::{name}#{start_line}",
                    chunk_type="function",
                    name=name,
                    start_line=start_line,
                    end_line=end_line,
                    code=code,
                    language=language,
                    metadata={"detector": "regex"},
                )
            )
        return out

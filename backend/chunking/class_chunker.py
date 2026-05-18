"""
Class-level chunker.

For Python, walks the AST and emits one chunk per top-level class.
For other languages, uses a `class Name { ... }` regex heuristic and pairs
braces to delimit the class body.

Falls back to a single whole-file chunk if no classes are found so the
SLM still has something to review.
"""

import ast
import re
from typing import List

from chunking.base import BaseChunker, CodeChunk

_BRACE_CLASS_RE = re.compile(
    r"^\s*(?:export\s+)?(?:public\s+|private\s+|protected\s+|abstract\s+|final\s+|static\s+|\s)*"
    r"class\s+([A-Za-z_][\w]*)\b",
    re.MULTILINE,
)


class ClassChunker(BaseChunker):
    strategy_id = "class"

    def chunk(self, source: str, language: str, file_name: str) -> List[CodeChunk]:
        if language == "python":
            chunks = self._chunk_python(source, file_name)
        else:
            chunks = self._chunk_brace_lang(source, language, file_name)

        if not chunks:
            lines = source.splitlines()
            chunks = [
                CodeChunk(
                    chunk_id=f"{file_name}::module",
                    chunk_type="class",
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
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                start = node.lineno
                end = node.end_lineno or start
                out.append(
                    CodeChunk(
                        chunk_id=f"{file_name}::{node.name}#{start}",
                        chunk_type="class",
                        name=node.name,
                        start_line=start,
                        end_line=end,
                        code="\n".join(lines[start - 1 : end]),
                        language="python",
                    )
                )
        return out

    def _chunk_brace_lang(self, source: str, language: str, file_name: str) -> List[CodeChunk]:
        lines = source.splitlines()
        out: List[CodeChunk] = []
        for match in _BRACE_CLASS_RE.finditer(source):
            name = match.group(1)
            start_offset = match.start()
            start_line = source.count("\n", 0, start_offset) + 1

            # Walk forward from the first `{` after the match to find the
            # matching closing `}` using simple brace depth.
            open_idx = source.find("{", match.end())
            if open_idx == -1:
                continue
            depth = 0
            end_idx = open_idx
            for i in range(open_idx, len(source)):
                ch = source[i]
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        end_idx = i
                        break
            end_line = source.count("\n", 0, end_idx) + 1
            out.append(
                CodeChunk(
                    chunk_id=f"{file_name}::{name}#{start_line}",
                    chunk_type="class",
                    name=name,
                    start_line=start_line,
                    end_line=end_line,
                    code="\n".join(lines[start_line - 1 : end_line]),
                    language=language,
                    metadata={"detector": "brace-pairing"},
                )
            )
        return out

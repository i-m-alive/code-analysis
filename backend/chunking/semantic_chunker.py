"""
Semantic chunker (embedding-free heuristic).

We don't use embeddings — that's intentional. Instead this chunker groups
code into logical blocks based on:

- For Python: top-level statements grouped into "imports", per-function,
  per-class, and any other free-standing top-level block.
- For other languages: split on stretches of >= 2 consecutive blank lines,
  which empirically correspond to author-chosen logical boundaries.

Falls back to a single whole-file chunk if no boundaries are detected.
"""

import ast
from typing import List

from chunking.base import BaseChunker, CodeChunk


class SemanticChunker(BaseChunker):
    strategy_id = "semantic"

    def chunk(self, source: str, language: str, file_name: str) -> List[CodeChunk]:
        if language == "python":
            chunks = self._chunk_python(source, file_name)
        else:
            chunks = self._chunk_blank_line(source, language, file_name)

        if not chunks:
            lines = source.splitlines()
            chunks = [
                CodeChunk(
                    chunk_id=f"{file_name}::module",
                    chunk_type="semantic",
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

        import_buf: List[ast.stmt] = []
        other_buf: List[ast.stmt] = []

        def flush_imports():
            if not import_buf:
                return
            start = import_buf[0].lineno
            end = import_buf[-1].end_lineno or start
            out.append(
                CodeChunk(
                    chunk_id=f"{file_name}::imports#{start}",
                    chunk_type="semantic",
                    name="imports",
                    start_line=start,
                    end_line=end,
                    code="\n".join(lines[start - 1 : end]),
                    language="python",
                    metadata={"group": "imports"},
                )
            )
            import_buf.clear()

        def flush_other():
            if not other_buf:
                return
            start = other_buf[0].lineno
            end = other_buf[-1].end_lineno or start
            out.append(
                CodeChunk(
                    chunk_id=f"{file_name}::top#{start}",
                    chunk_type="semantic",
                    name="top_level",
                    start_line=start,
                    end_line=end,
                    code="\n".join(lines[start - 1 : end]),
                    language="python",
                    metadata={"group": "top_level"},
                )
            )
            other_buf.clear()

        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                flush_other()
                import_buf.append(node)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                flush_imports()
                flush_other()
                start = node.lineno
                end = node.end_lineno or start
                out.append(
                    CodeChunk(
                        chunk_id=f"{file_name}::{node.name}#{start}",
                        chunk_type="semantic",
                        name=node.name,
                        start_line=start,
                        end_line=end,
                        code="\n".join(lines[start - 1 : end]),
                        language="python",
                        metadata={"group": "definition"},
                    )
                )
            else:
                flush_imports()
                other_buf.append(node)
        flush_imports()
        flush_other()
        return out

    def _chunk_blank_line(self, source: str, language: str, file_name: str) -> List[CodeChunk]:
        lines = source.splitlines()
        if not lines:
            return []

        blocks: List[tuple[int, int]] = []
        start = None
        blank_streak = 0
        for i, line in enumerate(lines, start=1):
            if line.strip() == "":
                blank_streak += 1
                # Two or more blanks finalize the current block.
                if blank_streak >= 2 and start is not None:
                    blocks.append((start, i - blank_streak))
                    start = None
            else:
                if start is None:
                    start = i
                blank_streak = 0
        if start is not None:
            blocks.append((start, len(lines)))

        out: List[CodeChunk] = []
        for idx, (s, e) in enumerate(blocks):
            out.append(
                CodeChunk(
                    chunk_id=f"{file_name}::semantic_{idx}#{s}",
                    chunk_type="semantic",
                    name=f"block_{idx}",
                    start_line=s,
                    end_line=e,
                    code="\n".join(lines[s - 1 : e]),
                    language=language,
                    metadata={"detector": "blank-line"},
                )
            )
        return out

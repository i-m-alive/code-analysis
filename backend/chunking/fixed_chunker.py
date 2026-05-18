"""
Fixed-size (line-window) chunker.

Slides a fixed-size window over the file with optional overlap so context
isn't lost at chunk boundaries. Always returns at least one chunk.
"""

from typing import List

from chunking.base import BaseChunker, CodeChunk


class FixedChunker(BaseChunker):
    strategy_id = "fixed"

    def __init__(self, window: int = 40, overlap: int = 5):
        self.window = window
        self.overlap = overlap

    def chunk(self, source: str, language: str, file_name: str) -> List[CodeChunk]:
        lines = source.splitlines()
        if not lines:
            return []

        chunks: List[CodeChunk] = []
        step = max(1, self.window - self.overlap)
        idx = 0
        block = 0
        while idx < len(lines):
            end = min(idx + self.window, len(lines))
            chunks.append(
                CodeChunk(
                    chunk_id=f"{file_name}::block_{block}#{idx + 1}",
                    chunk_type="fixed",
                    name=f"block_{block}",
                    start_line=idx + 1,
                    end_line=end,
                    code="\n".join(lines[idx:end]),
                    language=language,
                    metadata={"window": self.window, "overlap": self.overlap},
                )
            )
            if end == len(lines):
                break
            idx += step
            block += 1
        return chunks

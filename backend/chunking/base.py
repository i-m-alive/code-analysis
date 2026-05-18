"""
Common chunk data structure and abstract chunker interface.
"""

from dataclasses import dataclass, field
from typing import List


@dataclass
class CodeChunk:
    chunk_id: str
    chunk_type: str  # "function" | "class" | "fixed" | "semantic"
    name: str        # e.g. function or class name; "block_N" for fixed
    start_line: int
    end_line: int
    code: str
    language: str
    metadata: dict = field(default_factory=dict)


class BaseChunker:
    """All chunkers must produce a list of CodeChunk objects."""

    strategy_id: str = "base"

    def chunk(self, source: str, language: str, file_name: str) -> List[CodeChunk]:
        raise NotImplementedError

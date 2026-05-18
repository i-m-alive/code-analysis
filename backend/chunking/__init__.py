"""
Chunking package.

Exposes a single factory: get_chunker(strategy_id).

IMPORTANT: file-wise chunking is intentionally NOT implemented.
All four strategies — function, fixed, class, semantic — are registered
so the UI can offer them in a dropdown and we can benchmark them.
"""

from chunking.class_chunker import ClassChunker
from chunking.fixed_chunker import FixedChunker
from chunking.function_chunker import FunctionChunker
from chunking.semantic_chunker import SemanticChunker

_REGISTRY = {
    "function": FunctionChunker,
    "fixed": FixedChunker,
    "class": ClassChunker,
    "semantic": SemanticChunker,
}


def get_chunker(strategy_id: str):
    chunker_cls = _REGISTRY.get(strategy_id, FunctionChunker)
    return chunker_cls()

"""
Chunking package.

Exposes a single factory: get_chunker(strategy_id).

IMPORTANT: file-wise chunking is intentionally NOT implemented.
All four strategies — function, fixed, class, semantic — are registered
so the UI can offer them in a dropdown and we can benchmark them.

All strategies are backed by TreeSitterChunker, which uses real CST parsing
for every supported language and falls back to fixed-window splitting when
a grammar package is not installed.
"""

from functools import partial

from chunking.tree_sitter_chunker import TreeSitterChunker

_REGISTRY = {
    "comprehensive": partial(TreeSitterChunker, strategy="comprehensive"),
    "function":      partial(TreeSitterChunker, strategy="function"),
    "fixed":         partial(TreeSitterChunker, strategy="fixed"),
    "class":         partial(TreeSitterChunker, strategy="class"),
    "semantic":      partial(TreeSitterChunker, strategy="semantic"),
}


def get_chunker(strategy_id: str):
    factory = _REGISTRY.get(strategy_id, partial(TreeSitterChunker, strategy="comprehensive"))
    return factory()

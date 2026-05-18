"""
File-related helpers: language detection by extension and safe file I/O.
"""

from pathlib import Path

# Minimal extension -> language map. Extend as new languages are supported.
EXTENSION_LANGUAGE_MAP = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
    ".go": "go",
    ".rb": "ruby",
    ".cs": "csharp",
    ".cpp": "cpp",
    ".c": "c",
    ".rs": "rust",
}


def detect_language(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    return EXTENSION_LANGUAGE_MAP.get(suffix, "unknown")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")

"""
Ingestion Agent
===============
Responsible for:
- File parsing (reading text from disk)
- Language detection (by extension)
- Chunking (delegated to the chunking package)

The output is a list of CodeChunk objects ready to feed into the
Universal Review Agent.
"""

import logging
from pathlib import Path
from typing import List

from chunking import get_chunker
from chunking.base import CodeChunk
from utils.file_utils import detect_language, read_text

logger = logging.getLogger("ura.ingest")


class IngestionAgent:
    """Single-agent helper. Not a multi-agent component."""

    def ingest(
        self,
        file_path: Path,
        chunking_strategy: str,
        relative_path: str = None,
    ) -> tuple[str, str, List[CodeChunk]]:
        """
        Returns: (file_name, language, chunks)

        relative_path, when provided, is used as file_name so that folder
        structure (e.g. "MyProject/src/utils.py") is preserved in results.
        """
        file_name = relative_path or file_path.name
        basename = Path(file_name).name
        language = detect_language(basename)
        source = read_text(file_path)
        line_count = len(source.splitlines())
        logger.debug(
            "Parsed %s | %s | %d lines | %d bytes",
            file_name,
            language,
            line_count,
            len(source),
        )
        chunker = get_chunker(chunking_strategy)
        chunks = chunker.chunk(source, language, file_name)
        logger.debug(
            "Chunker '%s' produced %d chunk(s) for %s",
            chunking_strategy,
            len(chunks),
            file_name,
        )
        return file_name, language, chunks

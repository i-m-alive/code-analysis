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
    ) -> tuple[str, str, List[CodeChunk]]:
        """
        Returns: (file_name, language, chunks)
        """
        file_name = file_path.name
        language = detect_language(file_name)
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

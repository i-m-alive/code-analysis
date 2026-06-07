"""
POST /upload — accept source files, folders, or a .zip archive.

ZIP files are extracted server-side. Each member is saved with its full
internal relative path (e.g. "my-project/src/utils.py") stored in a .meta
sidecar so the analyze endpoint can reconstruct the folder tree.

Junk paths (node_modules, .git, __pycache__, *.pyc, .DS_Store …) are
silently skipped during extraction. Nested .zip files are not extracted.
"""

import io
import logging
import uuid
import zipfile
from pathlib import Path
from typing import List

from fastapi import APIRouter, File, Form, UploadFile

from config import UPLOAD_DIR
from utils.file_utils import detect_language

router = APIRouter()
logger = logging.getLogger("ura.upload")

_JUNK_DIRS = frozenset({
    "node_modules", ".git", "__pycache__", "__MACOSX",
    ".idea", ".vscode", ".pytest_cache", ".mypy_cache",
    "venv", ".venv", "env", "dist", "build",
})
_JUNK_EXTENSIONS = frozenset({".pyc", ".pyo", ".class"})
_JUNK_NAMES = frozenset({".DS_Store", "Thumbs.db", ".gitkeep"})


def _is_junk(name: str) -> bool:
    """Return True for zip entries that should be skipped."""
    if name.endswith("/"):          # directory entry
        return True
    parts = Path(name).parts
    filename = parts[-1]
    if filename in _JUNK_NAMES:
        return True
    if Path(filename).suffix in _JUNK_EXTENSIONS:
        return True
    for part in parts[:-1]:        # intermediate directories
        if part in _JUNK_DIRS or part.startswith("."):
            return True
    return False


def _persist(content: bytes, relative_path: str, saved: list) -> None:
    """Write file + .meta sidecar to UPLOAD_DIR and append to saved list."""
    basename = Path(relative_path).name
    unique_name = f"{uuid.uuid4().hex[:8]}_{basename}"
    (UPLOAD_DIR / unique_name).write_bytes(content)
    (UPLOAD_DIR / f"{unique_name}.meta").write_text(relative_path, encoding="utf-8")
    lang = detect_language(basename)
    logger.info("Saved %s -> %s | %d bytes | %s", relative_path, unique_name, len(content), lang)
    saved.append({
        "file_id": unique_name,
        "file_name": relative_path,
        "size_bytes": len(content),
        "language": lang,
    })


@router.post("/upload")
async def upload(
    files: List[UploadFile] = File(...),
    relative_paths: List[str] = Form(default=[]),
) -> dict:
    saved = []

    for i, upload_file in enumerate(files):
        relative_path = (
            relative_paths[i].strip()
            if i < len(relative_paths) and relative_paths[i].strip()
            else upload_file.filename
        )
        content = await upload_file.read()

        # ZIP: extract each member individually, skip junk + nested zips.
        if Path(relative_path).suffix.lower() == ".zip":
            try:
                with zipfile.ZipFile(io.BytesIO(content)) as zf:
                    for info in zf.infolist():
                        if _is_junk(info.filename):
                            continue
                        if Path(info.filename).suffix.lower() == ".zip":
                            continue   # skip nested zips
                        member_bytes = zf.read(info.filename)
                        if not member_bytes:
                            continue   # skip empty entries
                        _persist(member_bytes, info.filename, saved)
            except zipfile.BadZipFile:
                logger.warning("Skipping invalid zip: %s", relative_path)
            continue

        # Regular file or folder file.
        _persist(content, relative_path, saved)

    return {"files": saved}

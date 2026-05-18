"""
POST /upload — accept one or more source files and save them to UPLOAD_DIR.

Returns a list of file metadata records (file_id, name, size, language).
The file_id is just the filename on disk under uploads/ so the analyze
endpoint can locate the file later.
"""

import logging
import uuid
from typing import List

from fastapi import APIRouter, File, UploadFile

from config import UPLOAD_DIR
from utils.file_utils import detect_language

router = APIRouter()
logger = logging.getLogger("ura.upload")


@router.post("/upload")
async def upload(files: List[UploadFile] = File(...)) -> dict:
    saved = []
    for upload in files:
        # Use a UUID prefix so duplicate uploads don't clobber each other.
        unique_name = f"{uuid.uuid4().hex[:8]}_{upload.filename}"
        target = UPLOAD_DIR / unique_name
        content = await upload.read()
        target.write_bytes(content)
        logger.info(
            "Uploaded %s -> %s | %d bytes | %s",
            upload.filename,
            unique_name,
            len(content),
            detect_language(upload.filename),
        )
        saved.append({
            "file_id": unique_name,
            "file_name": upload.filename,
            "size_bytes": len(content),
            "language": detect_language(upload.filename),
        })
    return {"files": saved}

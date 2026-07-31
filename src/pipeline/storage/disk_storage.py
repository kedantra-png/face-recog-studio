# -*- coding: utf-8 -*-
"""
Streaming Disk Storage & Security Sanitizer
-------------------------------------------
Handles chunked streaming file saves, SHA-256 hashing, magic byte verification,
and safe ZIP archive decompression with Directory Traversal & ZIP-bomb protection.
"""

import os
import io
import time
import uuid
import shutil
import hashlib
import zipfile
import logging
from typing import Tuple, List, Dict, Any, Optional
import aiofiles
from src.pipeline.config import settings


logger = logging.getLogger("pipeline.storage")

# Supported Magic Bytes
MAGIC_BYTES = {
    b"\xff\xd8\xff": "image/jpeg",
    b"\x89PNG\r\n\x1a\n": "image/png",
    b"RIFF": "image/webp",  # WEBP starts with RIFF
    b"II*\x00": "image/tiff",
    b"MM\x00*": "image/tiff",
    b"BM": "image/bmp",
    b"PK\x03\x04": "application/zip",
}

# Maximum uncompressed ZIP extraction limit (500 MB)
MAX_UNCOMPRESSED_ZIP_SIZE = 500 * 1024 * 1024


def generate_oordhwa_filename(original_filename: str, sha256_hash: str = "") -> str:
    """
    Generates a secure, unguessable obfuscated filename starting with 'oordhwa'.
    Format: oordhwa_<timestamp_hex>_<hash_or_uuid_8char>.<ext>
    Example: oordhwa_66ab0e1f_a8f92b4c.jpg
    """
    ext = os.path.splitext(original_filename)[1].lower()
    if not ext or len(ext) > 5:
        ext = ".jpg"
    ts_hex = f"{int(time.time()):x}"
    if sha256_hash:
        sub_hash = sha256_hash[:8]
    else:
        sub_hash = uuid.uuid4().hex[:8]
    return f"oordhwa_{ts_hex}_{sub_hash}{ext}"


class DiskStorage:
    def __init__(self):
        self.base_dir = settings.TEMP_DIR
        os.makedirs(self.base_dir, exist_ok=True)

    def get_job_dir(self, job_id: str) -> str:
        job_dir = os.path.join(self.base_dir, job_id)
        os.makedirs(job_dir, exist_ok=True)
        os.makedirs(os.path.join(job_dir, "original"), exist_ok=True)
        os.makedirs(os.path.join(job_dir, "chunks"), exist_ok=True)
        return job_dir

    async def save_chunk(self, job_id: str, file_id: str, chunk_index: int, chunk_bytes: bytes) -> str:
        """Saves an incoming chunk stream to disk."""
        job_dir = self.get_job_dir(job_id)
        chunk_dir = os.path.join(job_dir, "chunks", file_id)
        os.makedirs(chunk_dir, exist_ok=True)

        chunk_path = os.path.join(chunk_dir, f"chunk_{chunk_index:05d}")
        async with aiofiles.open(chunk_path, "wb") as f:
            await f.write(chunk_bytes)

        return chunk_path

    async def assemble_chunks(
        self,
        job_id: str,
        file_id: str,
        total_chunks: int,
        relative_path: str
    ) -> Tuple[str, str, int]:
        """
        Reassembles all chunks for a file, calculates SHA256 checksum,
        and renames file to unguessable oordhwa filename format.
        """
        job_dir = self.get_job_dir(job_id)
        chunk_dir = os.path.join(job_dir, "chunks", file_id)
        
        # Target output path
        safe_rel_path = self._sanitize_path(relative_path)
        out_path = os.path.join(job_dir, "original", safe_rel_path)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)

        hasher = hashlib.sha256()
        total_bytes = 0

        async with aiofiles.open(out_path, "wb") as outfile:
            for i in range(total_chunks):
                chunk_path = os.path.join(chunk_dir, f"chunk_{i:05d}")
                if not os.path.exists(chunk_path):
                    raise FileNotFoundError(f"Missing chunk {i} for file {file_id}")

                async with aiofiles.open(chunk_path, "rb") as infile:
                    data = await infile.read()
                    hasher.update(data)
                    total_bytes += len(data)
                    await outfile.write(data)

        sha256_hash = hasher.hexdigest()
        oordhwa_name = generate_oordhwa_filename(relative_path, sha256_hash)
        oordhwa_path = os.path.join(os.path.dirname(out_path), oordhwa_name)

        if out_path != oordhwa_path:
            if os.path.exists(oordhwa_path):
                os.remove(oordhwa_path)
            os.rename(out_path, oordhwa_path)

        # Cleanup chunks folder only after successful assembly and renaming
        shutil.rmtree(chunk_dir, ignore_errors=True)

        return oordhwa_path, sha256_hash, total_bytes


    def validate_security(self, file_path: str) -> Tuple[bool, str]:
        """
        Validates magic bytes and rejects executables or corrupted files.
        """
        if not os.path.exists(file_path):
            return False, "File not found"

        with open(file_path, "rb") as f:
            header = f.read(16)

        is_valid = False
        mime_type = "unknown"
        for magic, mime in MAGIC_BYTES.items():
            if header.startswith(magic):
                is_valid = True
                mime_type = mime
                break

        if not is_valid:
            return False, f"Invalid or disallowed file signature (magic bytes)"

        return True, mime_type

    def extract_zip_safely(self, zip_path: str, job_id: str) -> List[Dict[str, Any]]:
        """
        Extracts ZIP files with Directory Traversal and ZIP-bomb protection.
        Renames extracted files to unguessable oordhwa filename format.
        """
        extracted_files = []
        job_dir = self.get_job_dir(job_id)
        dest_dir = os.path.join(job_dir, "original")

        total_extracted_size = 0

        with zipfile.ZipFile(zip_path, "r") as zf:
            for member in zf.infolist():
                # Protect against Directory Traversal
                member_name = member.filename
                if member_name.startswith("/") or ".." in member_name:
                    logger.warning(f"Skipping dangerous ZIP entry: {member_name}")
                    continue

                if member.is_dir():
                    continue

                # Protect against ZIP Bomb
                total_extracted_size += member.file_size
                if total_extracted_size > MAX_UNCOMPRESSED_ZIP_SIZE:
                    raise ValueError(f"ZIP bomb detected: Uncompressed size exceeds limit ({MAX_UNCOMPRESSED_ZIP_SIZE // (1024*1024)} MB)")

                # Extract safely
                target_path = os.path.join(dest_dir, self._sanitize_path(member_name))
                os.makedirs(os.path.dirname(target_path), exist_ok=True)

                with zf.open(member) as source, open(target_path, "wb") as target:
                    shutil.copyfileobj(source, target)

                # Calculate SHA256 for extracted file
                hasher = hashlib.sha256()
                with open(target_path, "rb") as f:
                    while chunk := f.read(65536):
                        hasher.update(chunk)
                sha256_hash = hasher.hexdigest()

                oordhwa_name = generate_oordhwa_filename(member_name, sha256_hash)
                oordhwa_path = os.path.join(os.path.dirname(target_path), oordhwa_name)
                if target_path != oordhwa_path:
                    if os.path.exists(oordhwa_path):
                        os.remove(oordhwa_path)
                    os.rename(target_path, oordhwa_path)

                extracted_files.append({
                    "file_path": oordhwa_path,
                    "relative_path": oordhwa_name,
                    "size": member.file_size,
                    "sha256": sha256_hash
                })

        return extracted_files


        return extracted_files

    def _sanitize_path(self, path_str: str) -> str:
        """Sanitizes relative folder path to prevent path traversal."""
        clean = os.path.normpath(path_str).lstrip("/\\")
        clean = clean.replace("..", "").strip()
        return clean or "uploaded_file"

    def cleanup_job_temp(self, job_id: str):
        """Removes temporary job directory after completion."""
        job_dir = os.path.join(self.base_dir, job_id)
        if os.path.exists(job_dir):
            shutil.rmtree(job_dir, ignore_errors=True)


disk_storage = DiskStorage()

"""Streaming storage helpers for developer package uploads.

Keep file I/O out of portal route handlers. Uploads are consumed in bounded
chunks so a large installer never has to exist as one in-memory bytes object.
"""

import hashlib
import secrets
from pathlib import Path
from typing import NamedTuple

from fastapi import UploadFile


UPLOAD_CHUNK_BYTES = 4 * 1024 * 1024
ALLOWED_EXTENSIONS = {".zip"}


class SavedUpload(NamedTuple):
    path: Path
    package_name: str
    sha256: str
    size: int


def safe_package_name(filename: str, fallback: str) -> str:
    name = (filename or fallback).replace("/", "_").replace("\\", "_").strip()
    name = name.lstrip(".")
    return name or fallback


def check_extension(name: str) -> None:
    suffix = Path(name).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise ValueError("安装包必须是 .zip 压缩包。请把工具打包成 zip 后再上传。")


async def save_upload_stream(
    upload: UploadFile,
    directory: Path,
    fallback_name: str,
    max_bytes: int,
    chunk_bytes: int = UPLOAD_CHUNK_BYTES,
) -> SavedUpload:
    """Persist an UploadFile incrementally and return its metadata.

    The temporary .part file is removed if the upload is empty, exceeds the
    configured maximum, or any read/write operation fails.
    """
    if max_bytes <= 0:
        raise ValueError("上传大小限制配置无效。")
    if chunk_bytes <= 0:
        raise ValueError("上传分块大小配置无效。")

    directory.mkdir(parents=True, exist_ok=True)
    package_name = safe_package_name(upload.filename or "", fallback_name)
    check_extension(package_name)
    token = secrets.token_hex(6)
    final_path = directory / f"{token}-{package_name}"
    part_path = directory / f".{token}-{package_name}.part"

    digest = hashlib.sha256()
    total = 0

    try:
        with part_path.open("wb") as output:
            while True:
                chunk = await upload.read(chunk_bytes)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise ValueError("安装包超过大小限制。")
                output.write(chunk)
                digest.update(chunk)

        if total <= 0:
            raise ValueError("安装包不能为空。")

        part_path.replace(final_path)
        return SavedUpload(
            path=final_path,
            package_name=package_name,
            sha256=digest.hexdigest(),
            size=total,
        )
    except Exception:
        part_path.unlink(missing_ok=True)
        final_path.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()

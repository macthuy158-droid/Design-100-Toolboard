"""CI checks for bounded-memory developer package storage."""

import asyncio
import hashlib
import io
from pathlib import Path
import shutil
import sys
import tempfile

from starlette.datastructures import UploadFile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from upload_storage import save_upload_stream  # noqa: E402


async def run_checks():
    root = Path(tempfile.mkdtemp(prefix="design100-upload-check-"))
    try:
        payload = (b"design100-streaming-upload" * 4096) + b"end"
        upload = UploadFile(filename="tool package.zip", file=io.BytesIO(payload))
        saved = await save_upload_stream(
            upload,
            root,
            fallback_name="fallback.zip",
            max_bytes=len(payload) + 1024,
            chunk_bytes=4096,
        )
        assert saved.path.exists(), "streamed package was not saved"
        assert saved.path.read_bytes() == payload, "saved package differs from source"
        assert saved.size == len(payload), "saved size is incorrect"
        assert saved.sha256 == hashlib.sha256(payload).hexdigest(), "SHA256 is incorrect"
        assert saved.package_name == "tool package.zip", "original safe filename should be retained"
        assert not list(root.glob("*.part")), "successful upload left a .part file"
        saved.path.unlink()

        too_large = UploadFile(filename="large.zip", file=io.BytesIO(b"x" * 8192))
        try:
            await save_upload_stream(
                too_large,
                root,
                fallback_name="large.zip",
                max_bytes=4096,
                chunk_bytes=1024,
            )
        except ValueError as exc:
            assert "超过大小限制" in str(exc)
        else:
            raise AssertionError("oversized upload was accepted")

        assert not list(root.iterdir()), "failed upload left residual files"
        print("Streaming upload checks passed")
        print("- chunked persistence")
        print("- SHA256 while streaming")
        print("- oversize cleanup")
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    asyncio.run(run_checks())

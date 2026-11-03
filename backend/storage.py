"""Filesystem adapter. HTTP routes do not need to know the on-disk layout.

A future cloud adapter can implement these same save/get/image_path operations
(or replace image_path with a download operation) without changing photo identity.
"""

import hashlib
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from .models import PhotoRecord


class PhotoConflict(Exception):
    """The same photo ID was submitted with different bytes or capture metadata."""


class LocalPhotoStore:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def get(self, photo_id: UUID) -> PhotoRecord:
        # Only canonical UUIDs become path components; uploaded filenames are ignored.
        metadata = self.root / str(photo_id) / "metadata.json"
        return PhotoRecord.model_validate_json(metadata.read_text(encoding="utf-8"))

    def image_path(self, photo_id: UUID) -> Path:
        return self.root / str(photo_id) / "image.png"

    def save(self, photo_id: UUID, captured_at: datetime, data: bytes,
             width: int, height: int) -> tuple[PhotoRecord, bool]:
        """Commit image and metadata together; identical retries are idempotent."""
        digest = hashlib.sha256(data).hexdigest()
        target = self.root / str(photo_id)

        def existing() -> tuple[PhotoRecord, bool]:
            record = self.get(photo_id)
            if record.sha256 != digest or record.captured_at != captured_at:
                raise PhotoConflict()
            return record, True

        if target.exists():
            return existing()

        record = PhotoRecord(
            id=photo_id, captured_at=captured_at,
            received_at=datetime.now(timezone.utc), size_bytes=len(data),
            width=width, height=height, sha256=digest,
        )
        # Stage both files in the same filesystem. Readers see the UUID directory
        # only after rename succeeds, never a half-written public record.
        temporary = Path(tempfile.mkdtemp(prefix=".upload-", dir=self.root))
        try:
            (temporary / "image.png").write_bytes(data)
            (temporary / "metadata.json").write_text(
                record.model_dump_json(indent=2), encoding="utf-8"
            )
            try:
                temporary.rename(target)
            except OSError:
                # Another request may have committed this ID while we were writing.
                # A completed target is nonempty, so rename cannot replace it.
                if target.exists():
                    return existing()
                raise
            return record, False
        finally:
            # Clean up failed/duplicate staging directories. Successful renames
            # have already moved the directory, so no cleanup is necessary.
            if temporary.exists():
                shutil.rmtree(temporary)

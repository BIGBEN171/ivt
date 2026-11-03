"""Public response models: these define the contract future clients can rely on."""

from uuid import UUID
from pydantic import AwareDatetime, BaseModel


class PhotoRecord(BaseModel):
    # Reuse the frontend Photo.id as the upload identity, including on retries.
    id: UUID
    captured_at: AwareDatetime
    received_at: AwareDatetime
    content_type: str = "image/png"
    size_bytes: int
    width: int
    height: int
    sha256: str


class UploadReceipt(BaseModel):
    photo: PhotoRecord
    # A matching retry returns the original record rather than storing a new photo.
    duplicate: bool

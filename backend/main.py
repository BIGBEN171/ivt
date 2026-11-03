"""FastAPI entry point: validate HTTP input, call storage, return typed responses.

Run from the repository root with:
    python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
No React code imports this module; frontend/backend communicate only through HTTP.
"""

import io
import logging
import warnings
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID

from fastapi import FastAPI, File, Form, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from PIL import Image, UnidentifiedImageError
from pydantic import AwareDatetime

from .config import Settings
from .models import PhotoRecord, UploadReceipt
from .storage import LocalPhotoStore, PhotoConflict

logger = logging.getLogger(__name__)


def validate_png(data: bytes, max_pixels: int) -> tuple[int, int]:
    """Check actual PNG contents rather than trusting the client filename/MIME."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                if image.format != "PNG":
                    raise HTTPException(415, "Only PNG images are accepted.")
                width, height = image.size
                if width * height > max_pixels:
                    raise HTTPException(413, "Image dimensions exceed the limit.")
                if getattr(image, "is_animated", False):
                    raise HTTPException(415, "Animated PNG is not supported.")
                image.verify()
            # verify checks structure; load additionally checks actual decoding.
            with Image.open(io.BytesIO(data)) as image:
                image.load()
        return width, height
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise HTTPException(413, "Image dimensions exceed the limit.") from None
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError):
        raise HTTPException(422, "The file is not a valid PNG image.") from None


def create_app(settings: Settings | None = None) -> FastAPI:
    """Factory allows tests to use temporary storage instead of real photo data."""
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        # Create writable storage at startup, not merely when importing this module.
        application.state.store = LocalPhotoStore(settings.data_dir)
        yield

    app = FastAPI(title="Clarity Capture API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware, allow_origins=list(settings.allowed_origins),
        allow_methods=["GET", "POST"], allow_headers=["Content-Type"],
    )

    @app.get("/api/v1/health")
    def health():
        """Liveness only: this does not claim cloud connectivity or free disk space."""
        return {"status": "ok", "storage": "local", "version": "0.1.0"}

    @app.post("/api/v1/photos", response_model=UploadReceipt, status_code=201)
    def upload_photo(
        response: Response,
        photo_id: Annotated[UUID, Form()],
        captured_at: Annotated[AwareDatetime, Form()],
        file: Annotated[UploadFile, File()],
    ):
        """Receive one frontend Photo using multipart form data.

        Send Photo.id as photo_id, Photo.capturedAt as captured_at and Photo.blob
        as file. UUID and timezone-aware timestamp validation is handled by FastAPI.
        This sync endpoint runs in a worker thread, keeping disk/decoding work off
        the async event loop. The original client filename is never used as a path.
        """
        try:
            # Read at most one byte beyond the application limit. Multipart parsing
            # happens earlier; production also needs an ingress request-size limit.
            data = file.file.read(settings.max_photo_bytes + 1)
        finally:
            file.file.close()
        if len(data) > settings.max_photo_bytes:
            raise HTTPException(413, "Photo exceeds the upload size limit.")
        width, height = validate_png(data, settings.max_pixels)
        try:
            record, duplicate = app.state.store.save(
                photo_id, captured_at, data, width, height
            )
        except PhotoConflict:
            raise HTTPException(409, "Photo ID already exists with different content.") from None
        except OSError:
            # Keep filesystem paths and low-level details out of public responses.
            logger.exception("Photo storage failed")
            raise HTTPException(503, "Photo storage is temporarily unavailable.") from None
        response.status_code = 200 if duplicate else 201
        return UploadReceipt(photo=record, duplicate=duplicate)

    @app.get("/api/v1/photos/{photo_id}", response_model=PhotoRecord)
    def get_photo(photo_id: UUID):
        """Read metadata; no patient identity or diagnostic result exists yet."""
        try:
            return app.state.store.get(photo_id)
        except FileNotFoundError:
            raise HTTPException(404, "Photo not found.") from None

    @app.get("/api/v1/photos/{photo_id}/image")
    def get_image(photo_id: UUID):
        """Return original PNG bytes for a future authorized viewing client."""
        get_photo(photo_id)
        return FileResponse(
            app.state.store.image_path(photo_id), media_type="image/png",
            headers={"Cache-Control": "no-store"},
        )

    return app


# The default app is local-development only: there is no authentication in this
# initial skeleton. Do not expose it publicly until access control is implemented.
app = create_app()

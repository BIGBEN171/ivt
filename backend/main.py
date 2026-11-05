"""FastAPI entry point: validate HTTP input, call storage, return typed responses.

Run from the repository root with:
    python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
No React code imports this module; frontend/backend communicate only through HTTP.
"""

import io
import logging
import warnings
import sqlite3
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID

from fastapi import FastAPI, File, Form, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, UnidentifiedImageError
from pydantic import AwareDatetime

from .config import Settings
from .models import PhotoRecord, UploadReceipt
from .storage import LocalPhotoStore, PhotoConflict
from .batches import BatchManifest, BatchStore
from pydantic import ValidationError

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
        application.state.batches = BatchStore(settings.data_dir)
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

    @app.post('/api/v1/batches', status_code=201)
    def upload_batch(response: Response, manifest: Annotated[str, Form()], files: Annotated[list[UploadFile], File()]):
        """Validate the entire burst before persisting any indexed batch."""
        try:
            try:
                batch = BatchManifest.model_validate_json(manifest)
            except ValidationError:
                raise HTTPException(422, 'Invalid batch metadata') from None
            if len(files) != 15:
                raise HTTPException(422, 'Exactly fifteen files are required')
            images = []
            for photo, file in zip(batch.photos, files):
                data = file.file.read(settings.max_photo_bytes + 1)
                if len(data) > settings.max_photo_bytes:
                    raise HTTPException(413, 'Photo exceeds the upload limit')
                if validate_png(data, settings.max_pixels) != (photo.width, photo.height):
                    raise HTTPException(422, 'Image dimensions do not match metadata')
                images.append(data)
            saved, duplicate = app.state.batches.save(batch, images)
            response.status_code = 200 if duplicate else 201
            return saved
        except PhotoConflict:
            raise HTTPException(409, 'Batch identity conflicts with stored content') from None
        except sqlite3.IntegrityError:
            raise HTTPException(409, 'Photo identity is already in use') from None
        except (OSError, sqlite3.Error):
            logger.exception('Batch storage failed')
            raise HTTPException(503, 'Local storage is unavailable') from None
        finally:
            for file in files:
                file.file.close()

    @app.get('/api/v1/batches')
    def list_batches():
        """Expose recent local sessions for a future operator history screen."""
        return app.state.batches.recent_batches()

    @app.get('/api/v1/batches/{batch_id}')
    def get_batch(batch_id: UUID):
        try:
            return app.state.batches.get(batch_id)
        except FileNotFoundError:
            raise HTTPException(404, 'Batch not found') from None

    @app.get('/api/v1/batches/{batch_id}/photos/{photo_id}')
    def batch_image(batch_id: UUID, photo_id: UUID):
        try:
            path = app.state.batches.image_path(batch_id, photo_id)
            if not path.is_file():
                raise FileNotFoundError()
            return FileResponse(path, media_type='image/png', headers={'Cache-Control': 'no-store'})
        except FileNotFoundError:
            raise HTTPException(404, 'Photo not found') from None

    # Mount the built React files last, preserving all explicit API routes above.
    # The Windows launcher builds these assets and binds Uvicorn to loopback only.
    frontend = Path(__file__).resolve().parent.parent / 'dist'
    if frontend.is_dir():
        app.mount('/', StaticFiles(directory=frontend, html=True), name='frontend')
    return app


# This single-computer prototype has no authentication; bind it to loopback only.
app = create_app()

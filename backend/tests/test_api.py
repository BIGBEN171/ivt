"""Exercise the HTTP contract with generated images and isolated temporary storage."""

import io
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from backend.config import Settings
from backend.main import create_app
from backend.storage import LocalPhotoStore


def png(color="red"):
    """Create synthetic test data; never read real patient photos."""
    buffer = io.BytesIO()
    Image.new("RGB", (4, 3), color).save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
def client(tmp_path):
    # The context manager runs lifespan startup/shutdown like a real server.
    with TestClient(create_app(Settings(data_dir=tmp_path))) as api:
        yield api


def upload(client, photo_id, content=None, captured_at="2026-11-03T00:00:00Z"):
    return client.post("/api/v1/photos", data={
        "photo_id": str(photo_id), "captured_at": captured_at,
    }, files={"file": ("../../untrusted.png", png() if content is None else content, "image/png")})


def test_round_trip_retry_and_conflict(client):
    photo_id = uuid4()
    response = upload(client, photo_id)
    assert response.status_code == 201
    record = response.json()["photo"]
    assert (record["width"], record["height"]) == (4, 3)
    assert client.get(f"/api/v1/photos/{photo_id}").json() == record
    assert client.get(f"/api/v1/photos/{photo_id}/image").content == png()
    # Lost responses can be retried safely using the original Photo.id.
    retry = upload(client, photo_id)
    assert retry.status_code == 200 and retry.json()["duplicate"] is True
    assert retry.json()["photo"] == record
    assert upload(client, photo_id, png("blue")).status_code == 409
    assert upload(client, photo_id, captured_at="2026-11-04T00:00:00Z").status_code == 409
    assert client.get(f"/api/v1/photos/{photo_id}/image").content == png()


@pytest.mark.parametrize("data", [b"", b"not an image", png()[:30]])
def test_reject_invalid_image(client, data):
    assert upload(client, uuid4(), data).status_code == 422


def test_validate_metadata_and_missing_record(client):
    assert upload(client, "not-a-uuid").status_code == 422
    assert upload(client, uuid4(), captured_at="2026-11-03T00:00:00").status_code == 422
    assert client.get(f"/api/v1/photos/{uuid4()}").status_code == 404
    assert client.get("/api/v1/health").json()["status"] == "ok"


def test_limits_and_format(tmp_path):
    # Check byte limits independently of image parsing.
    with TestClient(create_app(Settings(data_dir=tmp_path, max_photo_bytes=10))) as api:
        assert upload(api, uuid4()).status_code == 413
    with TestClient(create_app(Settings(data_dir=tmp_path, max_pixels=5))) as api:
        assert upload(api, uuid4()).status_code == 413
    buffer = io.BytesIO()
    Image.new("RGB", (2, 2)).save(buffer, format="JPEG")
    with TestClient(create_app(Settings(data_dir=tmp_path))) as api:
        assert upload(api, uuid4(), buffer.getvalue()).status_code == 415
    # Startup now initializes the batch database, but rejected uploads create no images.
    assert list(tmp_path.rglob('*.png')) == []


def test_storage_failure_is_not_success(client, monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("simulated disk failure")
    monkeypatch.setattr(client.app.state.store, "save", fail)
    response = upload(client, uuid4())
    assert response.status_code == 503
    assert "simulated" not in response.text


def test_concurrent_retries_commit_one_record(tmp_path):
    # Verify the adapter handles overlapping requests without overwriting a record.
    store = LocalPhotoStore(tmp_path)
    photo_id, captured_at = uuid4(), datetime.now(timezone.utc)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: store.save(photo_id, captured_at, png(), 4, 3), range(4)))
    assert sum(not duplicate for _, duplicate in results) == 1
    assert len(list(tmp_path.iterdir())) == 1
    assert store.image_path(photo_id).read_bytes() == png()


def test_cors_allows_local_frontend_only(client):
    headers = {"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"}
    assert client.options("/api/v1/photos", headers=headers).status_code == 200
    headers["Origin"] = "https://unconfigured.example"
    assert client.options("/api/v1/photos", headers=headers).status_code == 400

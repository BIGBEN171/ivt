"""Integration coverage for complete, durable, retry-safe fifteen-frame sessions."""
import io
import json
import sqlite3
from uuid import uuid4
from PIL import Image
from fastapi.testclient import TestClient
from backend.main import create_app
from backend.config import Settings


def payload():
    data = io.BytesIO()
    Image.new('RGB', (4, 3), 'green').save(data, format='PNG')
    manifest = {'id': str(uuid4()), 'photos': [dict(id=str(uuid4()), sequence=i+1,
        capturedAt='2026-11-06T00:00:00Z', mediaTimeMs=i*33.3,
        capturedMonotonicMs=100+i*33.3, presentedFrames=i+1, width=4, height=3) for i in range(15)]}
    return manifest, data.getvalue()


def send(client, manifest, image, count=15):
    return client.post('/api/v1/batches', data={'manifest': json.dumps(manifest)},
        files=[('files', (f'{i}.png', image, 'image/png')) for i in range(count)])


def test_batch_retry_restart_and_paths(tmp_path):
    manifest, image = payload()
    app = create_app(Settings(data_dir=tmp_path))
    with TestClient(app) as client:
        response = send(client, manifest, image)
        assert response.status_code == 201, response.text
        assert len(response.json()['photos']) == 15
        assert send(client, manifest, image).status_code == 200
    # Reopen the database through a new app to prove persistence beyond one process.
    with TestClient(create_app(Settings(data_dir=tmp_path))) as client:
        saved = client.get('/api/v1/batches/'+manifest['id']).json()
        for photo in saved['photos']:
            assert not photo['relative_path'].startswith(('/', '\\'))
            assert (tmp_path / photo['relative_path']).read_bytes() == image
            assert client.get(f"/api/v1/batches/{manifest['id']}/photos/{photo['id']}").content == image
        manifest['photos'][0]['capturedAt'] = '2026-11-06T01:00:00Z'
        assert send(client, manifest, image).status_code == 409
    with sqlite3.connect(tmp_path/'capture.db') as db:
        assert db.execute('SELECT count(*) FROM batch_photos').fetchone()[0] == 15


def test_partial_or_duplicate_frames_do_not_create_batch(tmp_path):
    manifest, image = payload()
    with TestClient(create_app(Settings(data_dir=tmp_path))) as client:
        assert send(client, manifest, image, 14).status_code == 422
        manifest['photos'][1]['mediaTimeMs'] = 0
        assert send(client, manifest, image).status_code == 422
        assert client.get('/api/v1/batches').json() == []
        assert list((tmp_path/'photos').iterdir()) == []


def test_interrupted_indexing_can_be_retried(tmp_path):
    manifest, image = payload()
    with TestClient(create_app(Settings(data_dir=tmp_path))) as client:
        assert send(client, manifest, image).status_code == 201
        # Simulate a crash after file publication but before the index commit.
        with sqlite3.connect(tmp_path/'capture.db') as db:
            db.execute('DELETE FROM batch_photos')
            db.execute('DELETE FROM batches')
        assert send(client, manifest, image).status_code == 201
        assert len(client.get('/api/v1/batches/'+manifest['id']).json()['photos']) == 15

"""SQLite batch index and local PNG files; no patient identity is stored.

Files are staged and renamed before the SQLite transaction is committed. A crash
between these operations may leave an unindexed folder. Its manifest allows an
identical retry to finish indexing without overwriting the original images.
"""
import hashlib
import json
import shutil
import sqlite3
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel, AwareDatetime, Field, model_validator
from .storage import PhotoConflict


class FrameMetadata(BaseModel):
    # Browser clocks describe sampling, not the sensor's exposure timestamp.
    id: UUID
    sequence: int = Field(ge=1, le=15)
    capturedAt: AwareDatetime
    mediaTimeMs: float = Field(ge=0, allow_inf_nan=False)
    capturedMonotonicMs: float = Field(ge=0, allow_inf_nan=False)
    presentedFrames: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class BatchManifest(BaseModel):
    id: UUID
    photos: list[FrameMetadata] = Field(min_length=15, max_length=15)

    @model_validator(mode='after')
    def ordered_frames(self):
        if [p.sequence for p in self.photos] != list(range(1, 16)) or len({p.id for p in self.photos}) != 15:
            raise ValueError('Expected fifteen unique, ordered photos')
        if any(b.mediaTimeMs <= a.mediaTimeMs or b.capturedMonotonicMs <= a.capturedMonotonicMs for a, b in zip(self.photos, self.photos[1:])):
            raise ValueError('Video and sampling times must increase')
        return self


class BatchStore:
    def __init__(self, root: Path):
        self.root = root
        self.photos = root / 'photos'
        self.photos.mkdir(parents=True, exist_ok=True)
        self.database = root / 'capture.db'
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS batches (
                    id TEXT PRIMARY KEY, created_at TEXT NOT NULL,
                    fingerprint TEXT NOT NULL, status TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS batch_photos (
                    id TEXT PRIMARY KEY, batch_id TEXT NOT NULL REFERENCES batches(id),
                    sequence INTEGER NOT NULL, relative_path TEXT NOT NULL,
                    captured_at TEXT NOT NULL, media_time_ms REAL NOT NULL,
                    sampled_ms REAL NOT NULL, width INTEGER NOT NULL, height INTEGER NOT NULL,
                    size_bytes INTEGER NOT NULL, sha256 TEXT NOT NULL,
                    UNIQUE(batch_id, sequence)
                );
            ''')

    @contextmanager
    def connect(self):
        # Each request owns a connection. IMMEDIATE transactions serialize writers.
        db = sqlite3.connect(self.database, timeout=30)
        db.execute('PRAGMA foreign_keys=ON')
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            # SQLite's transaction context alone does not close its file handle.
            db.close()

    def get(self, batch_id):
        with self.connect() as db:
            batch = db.execute('SELECT * FROM batches WHERE id=?', (str(batch_id),)).fetchone()
            if batch is None:
                raise FileNotFoundError()
            photos = db.execute('SELECT * FROM batch_photos WHERE batch_id=? ORDER BY sequence', (str(batch_id),)).fetchall()
        return {'id': batch['id'], 'status': batch['status'], 'photos': [dict(row) for row in photos]}

    def recent_batches(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute('SELECT id, created_at, status FROM batches ORDER BY created_at DESC LIMIT 100')]

    def image_path(self, batch_id, photo_id):
        with self.connect() as db:
            row = db.execute('SELECT relative_path FROM batch_photos WHERE id=? AND batch_id=?', (str(photo_id), str(batch_id))).fetchone()
        if row is None:
            raise FileNotFoundError()
        path = (self.root / row['relative_path']).resolve()
        if not path.is_relative_to(self.photos.resolve()):
            raise ValueError('Image path escaped the data directory')
        return path

    def save(self, manifest: BatchManifest, images: list[bytes]):
        hashes = [hashlib.sha256(image).hexdigest() for image in images]
        metadata = manifest.model_dump(mode='json')
        fingerprint = hashlib.sha256(json.dumps([metadata, hashes], sort_keys=True).encode()).hexdigest()
        target = self.photos / str(manifest.id)
        staged = Path(tempfile.mkdtemp(prefix='.batch-', dir=self.photos))
        try:
            for photo, image in zip(manifest.photos, images):
                with (staged / f'{photo.id}.png').open('wb') as output:
                    output.write(image)
                    output.flush()
                    # Flush image contents before recording a successful SQLite commit.
                    import os
                    os.fsync(output.fileno())
            (staged / 'manifest.json').write_text(json.dumps({'fingerprint': fingerprint, 'manifest': metadata, 'hashes': hashes}), encoding='utf-8')
            with self.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                existing = db.execute('SELECT fingerprint FROM batches WHERE id=?', (str(manifest.id),)).fetchone()
                if existing and existing['fingerprint'] != fingerprint:
                    raise PhotoConflict()
                if target.exists():
                    saved = json.loads((target / 'manifest.json').read_text(encoding='utf-8'))
                    if saved['fingerprint'] != fingerprint:
                        raise PhotoConflict()
                    # An identical retry also verifies that its original files still exist.
                    for photo, digest in zip(manifest.photos, hashes):
                        if hashlib.sha256((target / f'{photo.id}.png').read_bytes()).hexdigest() != digest:
                            raise OSError('Stored image integrity check failed')
                else:
                    staged.rename(target)
                if not existing:
                    db.execute('INSERT INTO batches VALUES (?, ?, ?, ?)', (str(manifest.id), datetime.now(timezone.utc).isoformat(), fingerprint, 'complete'))
                    for photo, image, digest in zip(manifest.photos, images, hashes):
                        relative = (Path('photos') / str(manifest.id) / f'{photo.id}.png').as_posix()
                        db.execute('INSERT INTO batch_photos VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', (str(photo.id), str(manifest.id), photo.sequence, relative, photo.capturedAt.isoformat(), photo.mediaTimeMs, photo.capturedMonotonicMs, photo.width, photo.height, len(image), digest))
            return self.get(manifest.id), bool(existing)
        finally:
            if staged.exists():
                shutil.rmtree(staged)

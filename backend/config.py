"""Server configuration, kept separate from HTTP routes and storage operations."""

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    # Resolve the default relative to this module, not the shell's current folder.
    # A future deployment can point this at a persistent server volume.
    data_dir: Path = field(default_factory=lambda: Path(
        os.environ.get("CAPTURE_DATA_DIR", Path(__file__).parent / "data")
    ).resolve())
    max_photo_bytes: int = 20 * 1024 * 1024
    max_pixels: int = 25_000_000
    # Only local development frontends are allowed by default. CORS is a browser
    # policy, NOT authentication; this prototype must remain on loopback.
    allowed_origins: tuple[str, ...] = (
        "http://127.0.0.1:5173", "http://localhost:5173",
    )

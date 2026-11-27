"""Media assets: content-addressed files with a rights record (DATABASE_SCHEMA §5, Phase 8).

Every file TubeForge makes or the owner gives it is stored once, by its SHA-256, under
``<data>/media/blobs/sha256/ab/cd/<sha>.<ext>``, and gets a ``media_assets`` row plus an
``asset_rights`` row in the same transaction. An asset without a rights record never enters a
render (CLAUDE.md): :func:`usable` is the one check renders and downloads use.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from tubeforge.db.ids import uuid7
from tubeforge.db.models import AssetRights, MediaAsset

EXTENSIONS: dict[str, str] = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}


@dataclass(frozen=True)
class Rights:
    """What may be done with an asset, recorded before anything uses it."""

    basis: str  # enum rights_basis
    licence_name: str
    commercial_use_allowed: bool
    licence_url: str | None = None
    attribution_required: bool = False
    attribution_text: str | None = None
    source_provider: str | None = None
    source_url: str | None = None
    lineage: dict[str, Any] = field(default_factory=dict)


def media_root(data_dir: Path) -> Path:
    return data_dir / "media" / "blobs" / "sha256"


def blob_path(data_dir: Path, sha256: str, mime_type: str) -> Path:
    ext = EXTENSIONS.get(mime_type, "bin")
    return media_root(data_dir) / sha256[:2] / sha256[2:4] / f"{sha256}.{ext}"


def write_blob(data_dir: Path, data: bytes, mime_type: str) -> tuple[str, Path]:
    """Store bytes once by content (atomic rename); returns (sha256, path)."""
    sha = hashlib.sha256(data).hexdigest()
    path = blob_path(data_dir, sha, mime_type)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + f".{uuid.uuid4().hex}.tmp")
        tmp.write_bytes(data)
        tmp.replace(path)
    return sha, path


def add_asset(
    db: Session,
    data_dir: Path,
    data: bytes,
    *,
    mime_type: str,
    kind: str,
    origin: str,
    rights: Rights,
    created_by: tuple[str, str],
    channel_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    width: int | None = None,
    height: int | None = None,
    retention_class: str = "MASTER",
) -> MediaAsset:
    """Store the file and add its asset and rights rows (flushed, not committed)."""
    if mime_type not in EXTENSIONS:
        raise ValueError(f"unsupported file type {mime_type}")
    sha, _ = write_blob(data_dir, data, mime_type)
    asset = MediaAsset(
        id=uuid7(),
        channel_id=channel_id,
        project_id=project_id,
        kind=kind,
        mime_type=mime_type,
        size_bytes=len(data),
        sha256=sha,
        width=width,
        height=height,
        origin=origin,
        retention_class=retention_class,
        created_by_type=created_by[0],
        created_by_id=created_by[1],
    )
    db.add(asset)
    db.flush()
    db.add(
        AssetRights(
            asset_id=asset.id,
            rights_basis=rights.basis,
            licence_name=rights.licence_name,
            licence_url=rights.licence_url,
            commercial_use_allowed=rights.commercial_use_allowed,
            attribution_required=rights.attribution_required,
            attribution_text=rights.attribution_text,
            source_provider=rights.source_provider,
            source_url=rights.source_url,
            lineage=rights.lineage,
        )
    )
    db.flush()
    return asset


def usable(db: Session, asset: MediaAsset) -> AssetRights | None:
    """The asset's rights record if the asset may be used at all (not deleted or quarantined)."""
    if asset.deleted_at is not None or asset.quarantined:
        return None
    return db.get(AssetRights, asset.id)


def read_blob(data_dir: Path, asset: MediaAsset) -> bytes:
    return blob_path(data_dir, asset.sha256, asset.mime_type).read_bytes()

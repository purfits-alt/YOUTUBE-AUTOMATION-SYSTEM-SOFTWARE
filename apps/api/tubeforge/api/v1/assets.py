"""Assets and channel art (Phase 8 step A; owner request 2026-11-15).

- Channel art: TubeForge draws 3 logos and 3 banners from the channel's blueprint (a heavy-worker
  job); the owner picks one of each and downloads them. TubeForge never uploads art to YouTube.
- Video watermark: the owner uploads their own brand logo (PNG, JPEG or WebP, ≤ 5 MB) and confirms
  it is theirs; a worker makes the 150 × 150 PNG.
- Downloads and the asset library only serve files that have a rights record.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from tubeforge.api.deps import Db, Principal, client_ip, request_id, require
from tubeforge.api.errors import ProblemError, not_found, problem_doc
from tubeforge.api.idempotency import Idempotency
from tubeforge.api.pagination import Limit, Page, clamp_limit
from tubeforge.api.v1.channels import get_channel, uuid_cursor
from tubeforge.api.v1.pipeline import JobProgressOut, job_out
from tubeforge.assets import EXTENSIONS, Rights, add_asset, blob_path, usable
from tubeforge.audit import record
from tubeforge.db.models import AssetRights, ChannelArt, ChannelStrategy, JobProgress, MediaAsset
from tubeforge.queue import defer_in_transaction

router = APIRouter(tags=["assets"])
View = Annotated[Principal, Depends(require("asset.view"))]
Edit = Annotated[Principal, Depends(require("asset.edit"))]
WRITE: dict[int | str, dict[str, Any]] = {
    409: problem_doc("NO_BLUEPRINT / NOT_FOUND"),
    413: problem_doc("TOO_LARGE: the file is over 5 MB"),
    415: problem_doc("UNSUPPORTED_TYPE: send a PNG, JPEG or WebP image"),
    422: problem_doc("CONFIRM_OWNERSHIP / IDEMPOTENCY_MISMATCH"),
}
MAX_LOGO_BYTES = 5 * 1024 * 1024
ART_JOBS = ("media.channel_art", "media.watermark")
Role = Literal["LOGO", "BANNER", "WATERMARK"]


# ------------------------------------------------------------------------------------- models
class ArtOut(BaseModel):
    id: uuid.UUID
    role: Role
    batch: int
    variant: int
    style: str
    chosen: bool
    asset_id: uuid.UUID
    width: int | None
    height: int | None
    size_bytes: int
    text_contrast: float | None
    licence: str
    download_url: str
    created_at: datetime


class BlueprintBrandOut(BaseModel):
    strategy_id: uuid.UUID
    status: str
    palette: list[str]
    default_tagline: str


class ChannelArtOut(BaseModel):
    channel_id: uuid.UUID
    channel_name: str
    blueprint: BlueprintBrandOut | None = Field(description="The blueprint the art is drawn from, if any.")
    logos: list[ArtOut] = Field(description="The newest batch of logos (800 × 800).")
    banners: list[ArtOut] = Field(description="The newest batch of banners (2560 × 1440).")
    chosen_logo: ArtOut | None
    chosen_banner: ArtOut | None
    watermark: ArtOut | None = Field(description="The 150 × 150 video watermark from the owner's logo.")
    job: JobProgressOut | None = Field(
        description="A channel-art or watermark job that is queued, running or just ended."
    )


class GenerateArtIn(BaseModel):
    tagline: Annotated[str, Field(max_length=90)] | None = Field(
        default=None, description="Banner tagline; empty uses a line from the blueprint's positioning."
    )


class QueuedOut(BaseModel):
    job_id: int | None


class AssetOut(BaseModel):
    id: uuid.UUID
    channel_id: uuid.UUID | None
    project_id: uuid.UUID | None
    kind: str
    origin: str
    mime_type: str
    size_bytes: int
    width: int | None
    height: int | None
    created_at: datetime
    rights_basis: str | None
    licence: str | None
    commercial_use_allowed: bool | None
    download_url: str | None = Field(description="Only for files with a rights record.")


# ------------------------------------------------------------------------------------ helpers
def _art_out(db: Session, row: ChannelArt) -> ArtOut:
    asset = db.get_one(MediaAsset, row.asset_id)
    rights = db.get(AssetRights, asset.id)
    lineage = rights.lineage if rights else {}
    contrast = lineage.get("text_contrast")
    return ArtOut(
        id=row.id,
        role=row.role,
        batch=row.batch,
        variant=row.variant,
        style=str(lineage.get("style") or ("Your logo" if row.role == "WATERMARK" else "")),
        chosen=row.chosen,
        asset_id=asset.id,
        width=asset.width,
        height=asset.height,
        size_bytes=asset.size_bytes,
        text_contrast=float(contrast) if contrast is not None else None,
        licence=rights.licence_name if rights else "",
        download_url=f"/api/v1/assets/{asset.id}/download",
        created_at=row.created_at,
    )


def _latest(db: Session, channel_id: uuid.UUID, role: str) -> list[ChannelArt]:
    batch = db.scalar(
        select(func.max(ChannelArt.batch)).where(ChannelArt.channel_id == channel_id, ChannelArt.role == role)
    )
    if batch is None:
        return []
    return list(
        db.scalars(
            select(ChannelArt)
            .where(ChannelArt.channel_id == channel_id, ChannelArt.role == role, ChannelArt.batch == batch)
            .order_by(ChannelArt.variant)
        )
    )


def _chosen(db: Session, channel_id: uuid.UUID, role: str) -> ChannelArt | None:
    return db.scalar(
        select(ChannelArt).where(
            ChannelArt.channel_id == channel_id, ChannelArt.role == role, ChannelArt.chosen.is_(True)
        )
    )


def _art_job(db: Session, channel_id: uuid.UUID) -> JobProgressOut | None:
    now = datetime.now(UTC)
    row = db.scalar(
        select(JobProgress)
        .where(JobProgress.entity_id == channel_id, JobProgress.kind.in_(ART_JOBS))
        .order_by(JobProgress.queued_at.desc())
        .limit(1)
    )
    if row is None or (row.finished_at is not None and now - row.finished_at > timedelta(minutes=10)):
        return None
    return job_out(db, row, now, {})


def channel_art_out(db: Session, channel_id: uuid.UUID) -> ChannelArtOut:
    from tubeforge_agents.discovery import channel_blueprint
    from tubeforge_media.channel_art import default_tagline

    channel = get_channel(db, channel_id)
    strategy: ChannelStrategy | None = channel_blueprint(db, channel_id)
    brand = (
        BlueprintBrandOut(
            strategy_id=strategy.id,
            status=strategy.status,
            palette=[str(p.get("hex")) for p in strategy.blueprint.get("brand", {}).get("palette", [])],
            default_tagline=default_tagline(strategy.blueprint),
        )
        if strategy is not None
        else None
    )
    chosen_logo, chosen_banner = _chosen(db, channel_id, "LOGO"), _chosen(db, channel_id, "BANNER")
    mark = _chosen(db, channel_id, "WATERMARK")
    return ChannelArtOut(
        channel_id=channel.id,
        channel_name=channel.name,
        blueprint=brand,
        logos=[_art_out(db, r) for r in _latest(db, channel_id, "LOGO")],
        banners=[_art_out(db, r) for r in _latest(db, channel_id, "BANNER")],
        chosen_logo=_art_out(db, chosen_logo) if chosen_logo else None,
        chosen_banner=_art_out(db, chosen_banner) if chosen_banner else None,
        watermark=_art_out(db, mark) if mark else None,
        job=_art_job(db, channel_id),
    )


def _audit(
    request: Request, db: Session, p: Principal, action: str, channel_id: uuid.UUID, **details: Any
) -> None:
    record(
        db,
        actor=p.actor,
        action=action,
        entity_type="channel",
        entity_id=str(channel_id),
        channel_id=channel_id,
        details=details,
        request_id=request_id(request),
        ip=client_ip(request),
    )


def _sniff(data: bytes) -> str | None:
    """The image type from the file's first bytes (the worker decodes it fully)."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def _data_dir(request: Request) -> Path:
    path: Path = request.app.state.settings.resolved_data_dir
    return path


# ------------------------------------------------------------------------------------- routes
@router.get("/channels/{channel_id}/channel-art", response_model=ChannelArtOut)
def get_channel_art(channel_id: uuid.UUID, db: Db, p: View) -> ChannelArtOut:
    """The newest logo and banner variants, the owner's picks and the watermark."""
    return channel_art_out(db, channel_id)


@router.post(
    "/channels/{channel_id}/channel-art/generate", response_model=QueuedOut, status_code=202, responses=WRITE
)
def generate_channel_art(
    channel_id: uuid.UUID, body: GenerateArtIn, request: Request, db: Db, p: Edit
) -> Any:
    """Queue 3 logos and 3 banners drawn from the channel's blueprint."""
    from tubeforge_agents.discovery import channel_blueprint

    idem = Idempotency(db, request, p.user.id, body)
    if (replayed := idem.replay()) is not None:
        return replayed
    get_channel(db, channel_id)
    if channel_blueprint(db, channel_id) is None:
        raise ProblemError(
            409,
            "NO_BLUEPRINT",
            "No blueprint",
            "This channel has no blueprint yet. Approve one for it first, so TubeForge knows its colours.",
        )
    tagline = (body.tagline or "").strip() or None
    job = defer_in_transaction(
        db, "media.channel_art", queue="heavy", args={"channel_id": str(channel_id), "tagline": tagline}
    )
    _audit(request, db, p, "channel_art.generate_requested", channel_id, tagline=tagline)
    out = QueuedOut(job_id=job)
    idem.store(202, out.model_dump(mode="json"))
    db.commit()
    return out


@router.post(
    "/channels/{channel_id}/channel-art/{art_id}/choose", response_model=ChannelArtOut, responses=WRITE
)
def choose_channel_art(
    channel_id: uuid.UUID, art_id: uuid.UUID, request: Request, db: Db, p: Edit
) -> ChannelArtOut:
    """Pick this logo or banner; the Branding Studio and the setup kit show it."""
    row = db.get(ChannelArt, art_id, with_for_update=True)
    if row is None or row.channel_id != channel_id or row.role == "WATERMARK":
        raise not_found("No such logo or banner for this channel.")
    db.execute(
        update(ChannelArt)
        .where(ChannelArt.channel_id == channel_id, ChannelArt.role == row.role, ChannelArt.id != row.id)
        .values(chosen=False)
    )
    db.flush()
    row.chosen = True
    _audit(
        request,
        db,
        p,
        "channel_art.chosen",
        channel_id,
        role=row.role,
        art_id=str(row.id),
        variant=row.variant,
    )
    db.commit()
    return channel_art_out(db, channel_id)


@router.post(
    "/channels/{channel_id}/watermark",
    response_model=QueuedOut,
    status_code=202,
    responses=WRITE,
    openapi_extra={
        "requestBody": {
            "required": True,
            "description": "Your own brand logo as the raw request body (PNG, JPEG or WebP, ≤ 5 MB).",
            "content": {mime: {"schema": {"type": "string", "format": "binary"}} for mime in EXTENSIONS},
        }
    },
)
async def upload_watermark_logo(
    channel_id: uuid.UUID,
    request: Request,
    db: Db,
    p: Edit,
    confirm_owned: Annotated[bool, Query(description="You confirm the logo is your own brand.")] = False,
) -> Any:
    """Upload the owner's own brand logo (e.g. SEMRS) and queue the 150 × 150 video watermark."""
    if not confirm_owned:
        raise ProblemError(
            422,
            "CONFIRM_OWNERSHIP",
            "Confirm the logo is yours",
            "Only your own brand logo can become the watermark. Tick the box to confirm it is yours.",
        )
    data = bytearray()
    async for chunk in request.stream():
        data += chunk
        if len(data) > MAX_LOGO_BYTES:
            raise ProblemError(413, "TOO_LARGE", "File too large", "The logo file must be 5 MB or smaller.")
    mime = _sniff(bytes(data))
    if mime is None:
        raise ProblemError(
            415, "UNSUPPORTED_TYPE", "Not an image", "Upload a PNG, JPEG or WebP image of your logo."
        )
    import hashlib

    idem = Idempotency(db, request, p.user.id, {"sha256": hashlib.sha256(data).hexdigest()})
    if (replayed := idem.replay()) is not None:
        return replayed
    get_channel(db, channel_id)
    source = add_asset(
        db,
        _data_dir(request),
        bytes(data),
        mime_type=mime,
        kind="IMAGE",
        origin="OWNER_UPLOAD",
        rights=Rights(
            basis="OWNER_CREATED",
            licence_name="Your own brand logo",
            commercial_use_allowed=True,
            lineage={"use": "video watermark source", "confirmed_by": str(p.user.id)},
        ),
        created_by=("USER", str(p.user.id)),
        channel_id=channel_id,
    )
    db.flush()
    rights = db.get_one(AssetRights, source.id)
    rights.verified_by, rights.verified_at = p.user.id, datetime.now(UTC)
    job = defer_in_transaction(
        db,
        "media.watermark",
        queue="heavy",
        args={"channel_id": str(channel_id), "source_asset_id": str(source.id)},
    )
    _audit(
        request,
        db,
        p,
        "channel_art.watermark_logo_uploaded",
        channel_id,
        asset_id=str(source.id),
        bytes=len(data),
    )
    out = QueuedOut(job_id=job)
    idem.store(202, out.model_dump(mode="json"))
    db.commit()
    return out


def _filename(db: Session, asset: MediaAsset) -> str:
    art = db.scalar(select(ChannelArt).where(ChannelArt.asset_id == asset.id))
    stem = f"{art.role.lower()}-{art.variant}" if art else f"asset-{str(asset.id)[:8]}"
    if art is not None:
        from tubeforge.db.models import Channel

        channel = db.get(Channel, art.channel_id)
        slug = re.sub(r"[^a-z0-9]+", "-", (channel.name if channel else "").lower()).strip("-")
        stem = f"{slug}-{stem}" if slug else stem
    return f"{stem}.{EXTENSIONS.get(asset.mime_type, 'bin')}"


@router.get(
    "/assets/{asset_id}/download",
    response_class=FileResponse,
    responses={200: {"content": {m: {} for m in EXTENSIONS}}, 404: problem_doc("NOT_FOUND")},
)
def download_asset(asset_id: uuid.UUID, request: Request, db: Db, p: View) -> FileResponse:
    """The file, if it has a rights record and is not deleted or quarantined."""
    asset = db.get(MediaAsset, asset_id)
    if asset is None or usable(db, asset) is None:
        raise not_found("No such file, or it has no rights record.")
    path = blob_path(_data_dir(request), asset.sha256, asset.mime_type)
    if not path.exists():
        raise not_found("The file is missing from the media folder.")
    return FileResponse(path, media_type=asset.mime_type, filename=_filename(db, asset))


@router.get("/assets", response_model=Page[AssetOut])
def list_assets(
    db: Db,
    p: View,
    channel_id: uuid.UUID | None = None,
    limit: Limit = None,
    cursor: Annotated[str | None, Query(pattern=r"^c[0-9]{1,40}$")] = None,
) -> Page[AssetOut]:
    """The asset library: every file with its rights summary, newest first."""
    n = clamp_limit(limit)
    stmt = (
        select(MediaAsset, AssetRights)
        .outerjoin(AssetRights, AssetRights.asset_id == MediaAsset.id)
        .where(MediaAsset.deleted_at.is_(None))
        .order_by(MediaAsset.id.desc())
    )
    if channel_id:
        stmt = stmt.where(MediaAsset.channel_id == channel_id)
    after = uuid_cursor(cursor)
    if after is not None:
        stmt = stmt.where(MediaAsset.id < after)
    rows = list(db.execute(stmt.limit(n + 1)).all())
    more = len(rows) > n
    rows = rows[:n]
    items = [
        AssetOut(
            id=a.id,
            channel_id=a.channel_id,
            project_id=a.project_id,
            kind=a.kind,
            origin=a.origin,
            mime_type=a.mime_type,
            size_bytes=a.size_bytes,
            width=a.width,
            height=a.height,
            created_at=a.created_at,
            rights_basis=r.rights_basis if r else None,
            licence=r.licence_name if r else None,
            commercial_use_allowed=r.commercial_use_allowed if r else None,
            download_url=f"/api/v1/assets/{a.id}/download" if r and not a.quarantined else None,
        )
        for a, r in rows
    ]
    return Page[AssetOut](items=items, next_cursor=f"c{rows[-1][0].id.int}" if more and rows else None)

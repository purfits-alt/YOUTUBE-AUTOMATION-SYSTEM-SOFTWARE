"""Upload jobs and quota status (BACKEND_SPECIFICATION §4.13)."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select

from tubeforge.api.deps import Db, Principal, require
from tubeforge.api.errors import not_found
from tubeforge.api.pagination import Cursor, Limit, Page, clamp_limit
from tubeforge.api.v1.channels import UploadJobOut, upload_out, uuid_cursor
from tubeforge.db.models import OAuthClient, QuotaConfig, UploadJob
from tubeforge.youtube import quota

router = APIRouter(tags=["uploads"])
UploadView = Annotated[Principal, Depends(require("upload.view"))]


class BucketOut(BaseModel):
    bucket: str
    daily_limit: int
    usable: int
    used: int
    held: int
    available: int
    resets_at: datetime
    resets_at_pkt: str


class ForecastOut(BaseModel):
    day: date
    planned_uploads: int
    upload_calls_left: int
    default_units_needed: int
    default_units_usable: int
    ok: bool


class ProjectQuotaOut(BaseModel):
    gcp_project: str
    buckets: list[BucketOut]
    forecast: list[ForecastOut]


@router.get("/uploads", response_model=Page[UploadJobOut])
def list_uploads(
    db: Db,
    _: UploadView,
    limit: Limit = None,
    cursor: Cursor = None,
    channel_id: uuid.UUID | None = None,
) -> Page[UploadJobOut]:
    n = clamp_limit(limit)
    stmt = select(UploadJob).order_by(UploadJob.id.desc()).limit(n + 1)
    if channel_id is not None:
        stmt = stmt.where(UploadJob.channel_id == channel_id)
    after = uuid_cursor(cursor)
    if after is not None:
        stmt = stmt.where(UploadJob.id < after)
    rows = list(db.scalars(stmt))
    more = len(rows) > n
    rows = rows[:n]
    return Page[UploadJobOut](
        items=[upload_out(r) for r in rows], next_cursor=f"c{rows[-1].id.int}" if more and rows else None
    )


@router.get("/uploads/{upload_id}", response_model=UploadJobOut)
def read_upload(upload_id: uuid.UUID, db: Db, _: UploadView) -> UploadJobOut:
    job = db.get(UploadJob, upload_id)
    if job is None:
        raise not_found("No such upload.")
    return upload_out(job)


@router.get("/quota", response_model=list[ProjectQuotaOut])
def quota_status(db: Db, _: UploadView) -> list[ProjectQuotaOut]:
    """Per Cloud project: today's buckets (PT day, reset shown in PKT) and the 7-day forecast."""
    now = datetime.now(UTC)
    projects = sorted(
        {c.gcp_project_id for c in db.scalars(select(OAuthClient)) if c.gcp_project_id}
        or {quota.DEFAULT_PROJECT}
    )
    today = quota.pt_day(now)
    days = [today + timedelta(days=i) for i in range(7)]
    planned = {
        d: int(
            db.scalar(
                select(func.count())
                .select_from(UploadJob)
                .where(
                    UploadJob.is_test.is_(False),
                    UploadJob.publish_at.is_not(None),
                    func.date(func.timezone("America/Los_Angeles", UploadJob.publish_at)) == d,
                )
            )
            or 0
        )
        for d in days
    }
    has_config = db.scalar(select(func.count()).select_from(QuotaConfig)) or 0
    out = []
    for project in projects:
        buckets = [BucketOut(**b.__dict__) for b in quota.status(db, project, now=now)]
        forecast = (
            [ForecastOut(**f.__dict__) for f in quota.forecast(db, project, planned)] if has_config else []
        )
        out.append(ProjectQuotaOut(gcp_project=project, buckets=buckets, forecast=forecast))
    return out

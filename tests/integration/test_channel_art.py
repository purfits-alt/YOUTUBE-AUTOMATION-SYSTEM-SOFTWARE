"""Channel art and the video watermark end to end (Phase 8 step A; owner request 2026-11-15).

Roadmap acceptance: logo 800×800 and banner 2560×1440 generated from the blueprint, each with a
rights record; the chosen files are what the Branding Studio and the setup kit show; they download
as PNG; TubeForge makes no YouTube call that changes the channel.
"""

from __future__ import annotations

import io
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from tubeforge_media import channel_art as ca

from tests.integration.conftest import Env, login
from tubeforge.db.ids import uuid7
from tubeforge.db.models import AssetRights, Channel, ChannelArt, ChannelStrategy, JobProgress, MediaAsset

pytestmark = pytest.mark.integration
BLUEPRINT = {
    "positioning": "Practical guides to running open AI models on your own computer.",
    "brand": {
        "palette": [
            {"hex": "#0F172A", "role": "Primary dark"},
            {"hex": "#F8FAFC", "role": "Light"},
            {"hex": "#22C55E", "role": "Accent"},
            {"hex": "#38BDF8", "role": "Secondary"},
        ],
        "contrast_pair": {"text": "#F8FAFC", "background": "#0F172A", "ratio": 17.85},
        "fonts": [{"family": "Inter", "use": "HEADLINE", "licence": "OFL-1.1"}],
    },
}


@pytest.fixture
def db(env: Env) -> Iterator[Session]:
    engine_ = create_engine(env.db_url)
    with Session(engine_, expire_on_commit=False) as s:
        yield s
    engine_.dispose()


@pytest.fixture
def api(env: Env) -> Iterator[tuple[TestClient, dict[str, str]]]:
    with env.client() as client:
        yield client, login(client)


def idem(h: dict[str, str]) -> dict[str, str]:
    return {**h, "Idempotency-Key": str(uuid.uuid4())}


def channel(db: Session, blueprint: bool = True) -> Channel:
    ch = Channel(id=uuid7(), name="Open Node AI", state="ACTIVE", content_language="en")
    db.add(ch)
    db.flush()
    if blueprint:
        db.add(
            ChannelStrategy(id=uuid7(), channel_id=ch.id, version=1, status="APPROVED", blueprint=BLUEPRINT)
        )
    db.commit()
    return ch


def logo_png() -> bytes:
    img = Image.new("RGBA", (600, 300), (0, 0, 0, 0))
    ImageDraw.Draw(img).ellipse((100, 50, 500, 250), fill=(10, 90, 200, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_generate_choose_and_download_channel_art(
    api: tuple[TestClient, dict[str, str]], db: Session, env: Env
) -> None:
    client, h = api
    data_dir: Path = env.app_settings.resolved_data_dir
    ch = channel(db)
    base = f"/api/v1/channels/{ch.id}/channel-art"
    empty = client.get(base).json()
    assert (empty["logos"], empty["banners"], empty["chosen_logo"], empty["watermark"]) == (
        [],
        [],
        None,
        None,
    )
    assert (
        empty["blueprint"]["default_tagline"]
        == "Practical guides to running open AI models on your own computer"
    )

    queued = client.post(f"{base}/generate", json={"tagline": "Open AI, on your own PC"}, headers=idem(h))
    assert queued.status_code == 202
    (args, queue) = env.sql(
        "SELECT args, queue_name FROM procrastinate_jobs WHERE task_name LIKE '%media.channel_art'"
    )[0]
    assert queue == "heavy" and args == {"channel_id": str(ch.id), "tagline": "Open AI, on your own PC"}
    assert client.get(base).json()["job"]["status"] == "QUEUED"  # shown live on the page and the Pipeline

    # The heavy worker draws them (called directly here).
    rows = ca.generate_channel_art(db, data_dir, ch.id, tagline="Open AI, on your own PC")
    db.commit()
    assert [(r.role, r.batch, r.variant) for r in rows] == [
        ("LOGO", 1, 1), ("LOGO", 1, 2), ("LOGO", 1, 3), ("BANNER", 1, 1), ("BANNER", 1, 2), ("BANNER", 1, 3),
    ]  # fmt: skip
    for row in rows:
        asset = db.get_one(MediaAsset, row.asset_id)
        rights = db.get_one(AssetRights, asset.id)
        assert (asset.kind, asset.origin, asset.mime_type, asset.channel_id) == (
            "IMAGE",
            "PROCEDURAL",
            "image/png",
            ch.id,
        )
        assert (rights.rights_basis, rights.commercial_use_allowed) == ("SYSTEM_GENERATED", True)
        assert rights.lineage["font"]["licence"] == "OFL-1.1" and rights.lineage["text_contrast"] >= 4.5
        size = (800, 800) if row.role == "LOGO" else (2560, 1440)
        with Image.open(io.BytesIO(ca.read_blob(data_dir, asset))) as img:
            assert img.size == size == (asset.width, asset.height)

    art = client.get(base).json()
    assert [a["variant"] for a in art["logos"]] == [1, 2, 3] and len(art["banners"]) == 3
    assert {a["style"] for a in art["banners"]} == {"Bold centre", "Gradient left", "Band"}

    # Pick logo 2, then banner 3; picking another logo moves the pick.
    pick = client.post(f"{base}/{art['logos'][1]['id']}/choose", headers=h).json()
    assert pick["chosen_logo"]["variant"] == 2
    client.post(f"{base}/{art['banners'][2]['id']}/choose", headers=h)
    pick = client.post(f"{base}/{art['logos'][0]['id']}/choose", headers=h).json()
    assert (pick["chosen_logo"]["variant"], pick["chosen_banner"]["variant"]) == (1, 3)
    chosen = db.scalars(
        select(ChannelArt).where(ChannelArt.channel_id == ch.id, ChannelArt.chosen.is_(True))
    ).all()
    assert sorted((c.role, c.variant) for c in chosen) == [("BANNER", 3), ("LOGO", 1)]

    # A second generation is a new batch; the picks stay until the owner picks again.
    ca.generate_channel_art(db, data_dir, ch.id)
    db.commit()
    again = client.get(base).json()
    assert {a["batch"] for a in again["logos"]} == {2} and again["chosen_logo"]["batch"] == 1

    file = client.get(pick["chosen_banner"]["download_url"])
    assert file.status_code == 200 and file.headers["content-type"] == "image/png"
    assert 'filename="open-node-ai-banner-3.png"' in file.headers["content-disposition"]
    assert file.content.startswith(b"\x89PNG")

    # An asset without a rights record is never served.
    bare = MediaAsset(
        id=uuid7(), kind="IMAGE", mime_type="image/png", size_bytes=1, sha256="0" * 64,
        origin="OWNER_UPLOAD", retention_class="MASTER", created_by_type="USER", created_by_id="x",
    )  # fmt: skip
    db.add(bare)
    db.commit()
    assert client.get(f"/api/v1/assets/{bare.id}/download").status_code == 404
    library = client.get(f"/api/v1/assets?channel_id={ch.id}").json()["items"]
    assert len(library) == 12 and all(a["download_url"] and a["licence"] for a in library)


def test_no_blueprint_and_bad_picks_are_refused(api: tuple[TestClient, dict[str, str]], db: Session) -> None:
    client, h = api
    ch = channel(db, blueprint=False)
    r = client.post(f"/api/v1/channels/{ch.id}/channel-art/generate", json={}, headers=idem(h))
    assert (r.status_code, r.json()["code"]) == (409, "NO_BLUEPRINT")
    assert client.post(f"/api/v1/channels/{ch.id}/channel-art/{uuid7()}/choose", headers=h).status_code == 404
    with pytest.raises(ca.ArtError, match="no blueprint"):
        ca.generate_channel_art(db, Path("/nonexistent"), ch.id)


def test_watermark_from_the_owners_own_logo(
    api: tuple[TestClient, dict[str, str]], db: Session, env: Env
) -> None:
    client, h = api
    data_dir: Path = env.app_settings.resolved_data_dir
    ch = channel(db)
    url = f"/api/v1/channels/{ch.id}/watermark"
    png = {**idem(h), "Content-Type": "image/png"}
    r = client.post(url, content=logo_png(), headers=png)
    assert (r.status_code, r.json()["code"]) == (422, "CONFIRM_OWNERSHIP")
    r = client.post(f"{url}?confirm_owned=true", content=b"%PDF-1.7 not an image", headers=idem(png))
    assert (r.status_code, r.json()["code"]) == (415, "UNSUPPORTED_TYPE")
    r = client.post(
        f"{url}?confirm_owned=true",
        content=b"\x89PNG\r\n\x1a\n" + b"0" * (5 * 1024 * 1024),
        headers=idem(png),
    )
    assert (r.status_code, r.json()["code"]) == (413, "TOO_LARGE")

    r = client.post(f"{url}?confirm_owned=true", content=logo_png(), headers=idem(png))
    assert r.status_code == 202
    (args,) = env.sql("SELECT args FROM procrastinate_jobs WHERE task_name LIKE '%media.watermark'")[0]
    source = db.get_one(MediaAsset, uuid.UUID(args["source_asset_id"]))  # type: ignore[index]
    rights = db.get_one(AssetRights, source.id)
    assert (source.origin, rights.rights_basis, rights.verified_by) == (
        "OWNER_UPLOAD",
        "OWNER_CREATED",
        env.owner.id,
    )
    assert db.scalar(select(JobProgress.kind).where(JobProgress.entity_id == ch.id)) == "media.watermark"

    mark = ca.make_watermark(db, data_dir, ch.id, source.id)
    db.commit()
    out = client.get(f"/api/v1/channels/{ch.id}/channel-art").json()["watermark"]
    assert (out["id"], out["width"], out["height"], out["chosen"]) == (str(mark.id), 150, 150, True)
    with Image.open(io.BytesIO(client.get(out["download_url"]).content)) as img:
        assert img.size == (150, 150) and img.mode == "RGBA"

    # Art TubeForge drew itself cannot become the watermark (only the owner's own logo).
    art = ca.generate_channel_art(db, data_dir, ch.id)
    db.commit()
    with pytest.raises(ca.ArtError, match="your own logo"):
        ca.make_watermark(db, data_dir, ch.id, art[0].asset_id)

"""Channel art drawn from the approved blueprint (owner request 2026-11-15, roadmap Phase 8 task 7).

- **Logo** 800 × 800 PNG, readable when YouTube crops it to a circle: everything stays inside the
  central circle. 3 variants.
- **Banner** 2560 × 1440 PNG: the name and tagline stay inside the area every device shows (the
  centre 1546 × 423), so TV, desktop and phone all show them. 3 variants.
- **Video watermark** 150 × 150 PNG made from the owner's own brand logo (transparent background).

Procedural only (Pillow): the blueprint's palette, the installed Source Sans Pro font (SIL OFL 1.1)
and the channel's name; no AI image model, no stock images. Text colour is chosen so it reaches at
least 4.5:1 contrast with what is behind it. TubeForge never uploads art to YouTube: the owner
downloads the chosen files and sets them in YouTube Studio.
"""

from __future__ import annotations

import io
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import font_source_sans_pro
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from tubeforge import progress
from tubeforge.assets import Rights, add_asset, read_blob, usable
from tubeforge.db.ids import uuid7
from tubeforge.db.models import Channel, ChannelArt, MediaAsset
from tubeforge.research.blueprint import contrast_ratio

LOGO_SIZE = 800
LOGO_SAFE_RADIUS = 340  # YouTube shows the logo as a circle; keep marks inside this radius
BANNER_SIZE = (2560, 1440)
#: Visible on every device: the centre 1546 × 423 (YouTube's banner guidance).
BANNER_SAFE = (507, 508, 2053, 931)
BANNER_PAD = 36
WATERMARK_SIZE = 150
MIN_CONTRAST = 4.5
VARIANTS = 3
MAX_UPLOAD_PIXELS = 40_000_000
RENDERER = "tubeforge_media.channel_art v1"
FONT = {
    "name": "Source Sans Pro",
    "licence": "OFL-1.1",
    "licence_url": "https://openfontlicense.org/open-font-license-official-text/",
    "package": "font-source-sans-pro 0.0.1",
}
#: Scripts Source Sans Pro can draw: Latin (incl. extended), Greek, Cyrillic, punctuation.
_DRAWABLE = re.compile(r"^[ -ɏͰ-ϿЀ-ӿ‐-›€]*$")


class ArtError(Exception):
    """Channel art could not be made; the message is for the owner."""


@dataclass(frozen=True)
class Brand:
    name: str
    tagline: str
    dark: str
    light: str
    accent: str
    palette: list[str]


@dataclass(frozen=True)
class Drawn:
    image: Image.Image
    text_boxes: list[tuple[int, int, int, int]]
    text_contrast: float
    style: str


# --------------------------------------------------------------------------------------- colours
def _rgb(hex_colour: str) -> tuple[int, int, int]:
    return int(hex_colour[1:3], 16), int(hex_colour[3:5], 16), int(hex_colour[5:7], 16)


def _hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02X}{:02X}{:02X}".format(*rgb)


def _mix(a: str, b: str, t: float) -> str:
    ra, rb = _rgb(a), _rgb(b)
    return _hex(
        (
            round(ra[0] + (rb[0] - ra[0]) * t),
            round(ra[1] + (rb[1] - ra[1]) * t),
            round(ra[2] + (rb[2] - ra[2]) * t),
        )
    )


def readable_mix(dark: str, accent: str, t: float, prefer: str | None = None) -> str:
    """The furthest blend from dark towards accent (≤ t) behind which text still reaches 4.5:1."""
    while t > 0.05:
        mixed = _mix(dark, accent, t)
        if text_colour(dark, mixed, prefer=prefer)[1] >= MIN_CONTRAST:
            return mixed
        t -= 0.05
    return dark


def text_colour(*backgrounds: str, prefer: str | None = None) -> tuple[str, float]:
    """The colour with the best worst-case contrast against every background (≥ 4.5 where possible)."""
    options = [c for c in (prefer, "#FFFFFF", "#111111") if c]
    best = max(options, key=lambda c: min(contrast_ratio(c, bg) for bg in backgrounds))
    return best, min(contrast_ratio(best, bg) for bg in backgrounds)


def brand_from(blueprint: dict[str, Any], name: str, tagline: str | None) -> Brand:
    brand = blueprint.get("brand", {})
    palette = [
        str(p["hex"]).upper()
        for p in brand.get("palette", [])
        if re.match(r"^#[0-9A-Fa-f]{6}$", str(p.get("hex")))
    ]
    pair = brand.get("contrast_pair") or {}
    if len(palette) < 2:
        palette = ["#1B1F3B", "#F5F3EE", "#E4572E", "#17BEBB"]
    by_lum = sorted(palette, key=lambda h: contrast_ratio(h, "#000000"))
    dark = str(pair.get("background") or by_lum[0]).upper()
    light = str(pair.get("text") or by_lum[-1]).upper()
    if contrast_ratio(dark, light) < MIN_CONTRAST:
        dark, light = by_lum[0], by_lum[-1]
    # Keep the palette's hue but make sure text can be read: deepen the dark colour and lighten the
    # light one until they reach strong contrast (a palette of mid tones would otherwise fail 4.5:1).
    for _ in range(20):
        if contrast_ratio(dark, "#FFFFFF") >= 7.0:
            break
        dark = _mix(dark, "#000000", 0.15)
    for _ in range(20):
        if contrast_ratio(light, dark) >= 7.0:
            break
        light = _mix(light, "#FFFFFF", 0.2)
    accents = [h for h in palette if h not in (dark, light)] or [light]
    accent = max(accents, key=_saturation)
    return Brand(
        name=name.strip(),
        tagline=(tagline or default_tagline(blueprint)).strip(),
        dark=dark,
        light=light,
        accent=accent,
        palette=palette,
    )


def _saturation(hex_colour: str) -> float:
    r, g, b = (c / 255 for c in _rgb(hex_colour))
    mx, mn = max(r, g, b), min(r, g, b)
    return 0.0 if mx == 0 else (mx - mn) / mx


def default_tagline(blueprint: dict[str, Any]) -> str:
    """A short line from the blueprint's positioning (else description), cut at a word."""
    text = str(blueprint.get("positioning") or blueprint.get("description") or "").strip()
    first = re.split(r"(?<=[.!?])\s", text, maxsplit=1)[0].rstrip(".")
    if len(first) <= 70:
        return first
    return first[:70].rsplit(" ", 1)[0].rstrip(",;:—-") + "…"


def initials(name: str) -> str:
    words = re.findall(r"[A-Z]?[a-z0-9]+|[A-Z]+(?![a-z])|\w+", name, flags=re.UNICODE)
    letters = [w[0].upper() for w in words if w and w[0].isalnum()]
    return "".join(letters[:2]) or name[:1].upper()


def check_drawable(*texts: str) -> None:
    for text in texts:
        if not _DRAWABLE.match(text):
            raise ArtError(
                f"“{text[:40]}” uses letters the installed font (Source Sans Pro) cannot draw. Urdu and "
                "other scripts arrive with the voice step of Phase 8; for now, change the tagline, or "
                "give the channel a Latin-letter name."
            )


# ------------------------------------------------------------------------------------------ fonts
def font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    key = {
        "black": "SourceSansProBlack",
        "bold": "SourceSansProBold",
        "semibold": "SourceSansProSemibold",
        "regular": "SourceSansPro",
    }[weight]
    return ImageFont.truetype(str(font_source_sans_pro.font_files_ttf[key]), size)


def fit(text: str, weight: str, max_w: int, max_h: int, start: int) -> ImageFont.FreeTypeFont:
    """The largest size ≤ start at which the text fits the box."""
    size = start
    while size > 12:
        f = font(weight, size)
        left, top, right, bottom = f.getbbox(text)
        if right - left <= max_w and bottom - top <= max_h:
            return f
        size = int(size * 0.92)
    return font(weight, 12)


def _draw_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[float, float],
    text: str,
    f: ImageFont.FreeTypeFont,
    fill: str,
    anchor: str,
) -> tuple[int, int, int, int]:
    draw.text(xy, text, font=f, fill=fill, anchor=anchor)
    box = draw.textbbox(xy, text, font=f, anchor=anchor)
    return int(box[0]), int(box[1]), int(box[2]), int(box[3])


def _gradient(size: tuple[int, int], a: str, b: str) -> Image.Image:
    """Left-to-right gradient from colour a to colour b."""
    strip = Image.new("RGB", (256, 1))
    for i in range(256):
        strip.putpixel((i, 0), _rgb(_mix(a, b, i / 255)))
    return strip.resize(size, Image.Resampling.BILINEAR)


def _diagonal(size: tuple[int, int], a: str, b: str) -> Image.Image:
    w, h = size
    img = Image.new("RGB", size)
    px = img.load()
    assert px is not None
    ra, rb = _rgb(a), _rgb(b)
    span = w + h - 2
    for y in range(h):
        for x in range(0, w, 4):
            t = (x + y) / span
            c = (
                round(ra[0] + (rb[0] - ra[0]) * t),
                round(ra[1] + (rb[1] - ra[1]) * t),
                round(ra[2] + (rb[2] - ra[2]) * t),
            )
            for dx in range(4):
                if x + dx < w:
                    px[x + dx, y] = c
    return img


# ------------------------------------------------------------------------------------------- logo
def logo(brand: Brand, variant: int) -> Drawn:
    """800 × 800; every mark stays inside the central circle YouTube shows."""
    size, c = LOGO_SIZE, LOGO_SIZE / 2
    mono = initials(brand.name)
    if variant == 1:  # monogram on dark with an accent ring
        img = Image.new("RGB", (size, size), brand.dark)
        d = ImageDraw.Draw(img)
        r = LOGO_SAFE_RADIUS - 10
        d.ellipse((c - r, c - r, c + r, c + r), outline=brand.accent, width=18)
        ink, ratio = text_colour(brand.dark, prefer=brand.light)
        f = fit(mono, "black", int(r * 1.15), int(r * 0.9), 420)
        box = _draw_text(d, (c, c), mono, f, ink, "mm")
        style = "Monogram ring"
    elif variant == 2:  # diagonal gradient, monogram, accent bar
        end = readable_mix(brand.dark, brand.accent, 0.55, prefer=brand.light)
        img = _diagonal((size, size), brand.dark, end)
        d = ImageDraw.Draw(img)
        ink, ratio = text_colour(brand.dark, end, prefer=brand.light)
        f = fit(mono, "bold", int(LOGO_SAFE_RADIUS * 1.3), int(LOGO_SAFE_RADIUS * 0.85), 400)
        box = _draw_text(d, (c, c - 20), mono, f, ink, "mm")
        d.rounded_rectangle((c - 90, box[3] + 30, c + 90, box[3] + 54), radius=12, fill=ink)
        style = "Gradient"
    else:  # light badge: filled disc with the monogram
        img = Image.new("RGB", (size, size), brand.light)
        d = ImageDraw.Draw(img)
        r = LOGO_SAFE_RADIUS - 30
        disc = brand.dark
        d.ellipse((c - r, c - r, c + r, c + r), fill=disc)
        d.ellipse((c - r - 22, c - r - 22, c + r + 22, c + r + 22), outline=brand.accent, width=8)
        ink, ratio = text_colour(disc, prefer=brand.light)
        f = fit(mono, "black", int(r * 1.2), int(r * 0.9), 380)
        box = _draw_text(d, (c, c), mono, f, ink, "mm")
        style = "Badge"
    return Drawn(img, [box], ratio, style)


# ----------------------------------------------------------------------------------------- banner
def banner(brand: Brand, variant: int) -> Drawn:
    """2560 × 1440; the name and tagline stay inside the centre 1546 × 423 every device shows."""
    w, h = BANNER_SIZE
    x0, y0, x1, y1 = BANNER_SAFE
    inner = (x0 + BANNER_PAD, y0 + BANNER_PAD, x1 - BANNER_PAD, y1 - BANNER_PAD)
    iw, ih = inner[2] - inner[0], inner[3] - inner[1]
    if variant == 1:  # solid dark, accent shapes outside the text area
        img = Image.new("RGB", (w, h), brand.dark)
        d = ImageDraw.Draw(img)
        d.polygon([(0, h), (0, h - 420), (620, h)], fill=brand.accent)
        d.polygon([(w, 0), (w, 420), (w - 620, 0)], fill=brand.accent)
        bg = [brand.dark]
        anchor_x, align = (inner[0] + inner[2]) / 2, "m"
        style = "Bold centre"
    elif variant == 2:  # horizontal gradient, circles at the sides, text left-aligned
        right = readable_mix(brand.dark, brand.accent, 0.45, prefer=brand.light)
        img = _gradient((w, h), brand.dark, right)
        d = ImageDraw.Draw(img, "RGBA")
        ar, ag, ab = _rgb(brand.accent)
        for cx, cy, r in ((180, 300, 340), (2400, 1200, 420), (2300, 180, 160)):
            d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(ar, ag, ab, 70))
        d.rectangle((inner[0], inner[1] + 10, inner[0] + 14, inner[3] - 10), fill=brand.accent)
        inner = (inner[0] + 44, inner[1], inner[2], inner[3])
        iw = inner[2] - inner[0]
        bg = [brand.dark, _mix(brand.dark, right, (inner[2] / w))]
        anchor_x, align = inner[0], "l"
        style = "Gradient left"
    else:  # light canvas, dark band behind the text
        img = Image.new("RGB", (w, h), brand.light)
        d = ImageDraw.Draw(img)
        d.rectangle((0, y0 - 40, w, y1 + 40), fill=brand.dark)
        d.rectangle((0, y1 + 40, w, y1 + 56), fill=brand.accent)
        bg = [brand.dark]
        anchor_x, align = (inner[0] + inner[2]) / 2, "m"
        style = "Band"
    d = ImageDraw.Draw(img)
    ink, ratio = text_colour(*bg, prefer=brand.light)
    title = fit(brand.name, "black", iw, int(ih * 0.62), 260)
    boxes: list[tuple[int, int, int, int]] = []
    if brand.tagline:
        tag = fit(brand.tagline, "semibold", iw, int(ih * 0.26), 84)
        t_h = title.getbbox(brand.name)[3] - title.getbbox(brand.name)[1]
        g_h = tag.getbbox(brand.tagline)[3] - tag.getbbox(brand.tagline)[1]
        gap = 24
        top = inner[1] + (ih - (t_h + gap + g_h)) / 2
        boxes.append(_draw_text(d, (anchor_x, top), brand.name, title, ink, f"{align}t"))
        boxes.append(_draw_text(d, (anchor_x, boxes[0][3] + gap), brand.tagline, tag, ink, f"{align}t"))
    else:
        boxes.append(
            _draw_text(d, (anchor_x, (inner[1] + inner[3]) / 2), brand.name, title, ink, f"{align}m")
        )
    return Drawn(img, boxes, ratio, style)


# -------------------------------------------------------------------------------------- watermark
def watermark(source: bytes) -> Image.Image:
    """150 × 150 PNG from the owner's logo: trimmed, fitted with a margin, transparent background."""
    Image.MAX_IMAGE_PIXELS = MAX_UPLOAD_PIXELS
    try:
        with Image.open(io.BytesIO(source)) as probe:
            probe.verify()
        opened = Image.open(io.BytesIO(source))
        opened.load()
    except (Image.DecompressionBombError, OSError, SyntaxError, ValueError) as exc:
        raise ArtError(
            "The logo file could not be read as an image. Upload a PNG, JPEG or WebP file."
        ) from exc
    img: Image.Image = opened.convert("RGBA")
    bbox = img.getchannel("A").getbbox()
    if bbox:
        img = img.crop(bbox)
    margin = 6
    img.thumbnail((WATERMARK_SIZE - 2 * margin, WATERMARK_SIZE - 2 * margin), Image.Resampling.LANCZOS)
    out = Image.new("RGBA", (WATERMARK_SIZE, WATERMARK_SIZE), (0, 0, 0, 0))
    out.paste(img, ((WATERMARK_SIZE - img.width) // 2, (WATERMARK_SIZE - img.height) // 2), img)
    return out


def png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


# ---------------------------------------------------------------------------------------- pipeline
def _rights(lineage: dict[str, Any]) -> Rights:
    return Rights(
        basis="SYSTEM_GENERATED",
        licence_name="Drawn by TubeForge from your blueprint; font Source Sans Pro (SIL OFL 1.1)",
        licence_url=FONT["licence_url"],
        commercial_use_allowed=True,
        lineage={"renderer": RENDERER, "font": FONT, **lineage},
    )


def _next_batch(db: Session, channel_id: uuid.UUID, role: str) -> int:
    current = db.scalar(
        select(func.coalesce(func.max(ChannelArt.batch), 0)).where(
            ChannelArt.channel_id == channel_id, ChannelArt.role == role
        )
    )
    return int(current or 0) + 1


def generate_channel_art(
    db: Session, data_dir: Path, channel_id: uuid.UUID, *, tagline: str | None = None
) -> list[ChannelArt]:
    """3 logos and 3 banners from the channel's blueprint, each a PROCEDURAL asset with rights."""
    from tubeforge_agents.discovery import channel_blueprint

    channel = db.get_one(Channel, channel_id)
    strategy = channel_blueprint(db, channel_id)
    if strategy is None:
        raise ArtError(
            "This channel has no blueprint yet. Approve a blueprint for it (Strategies, or the Build tab) "
            "so TubeForge knows its colours and style."
        )
    brand = brand_from(strategy.blueprint, channel.name, tagline)
    check_drawable(brand.name, brand.tagline)
    rows: list[ChannelArt] = []
    steps = 2 * VARIANTS
    for role, draw in (("LOGO", logo), ("BANNER", banner)):
        batch = _next_batch(db, channel_id, role)
        for variant in range(1, VARIANTS + 1):
            progress.report(5 + 90 * len(rows) // steps, f"Drawing {role.lower()} {variant} of {VARIANTS}")
            drawn = draw(brand, variant)
            data = png(drawn.image)
            asset = add_asset(
                db,
                data_dir,
                data,
                mime_type="image/png",
                kind="IMAGE",
                origin="PROCEDURAL",
                rights=_rights(
                    {
                        "role": role,
                        "variant": variant,
                        "style": drawn.style,
                        "blueprint_strategy_id": str(strategy.id),
                        "palette": brand.palette,
                        "text_contrast": round(drawn.text_contrast, 2),
                        "blueprint_fonts": strategy.blueprint.get("brand", {}).get("fonts", []),
                        "tagline": brand.tagline if role == "BANNER" else None,
                    }
                ),
                created_by=("SYSTEM", RENDERER),
                channel_id=channel_id,
                width=drawn.image.width,
                height=drawn.image.height,
            )
            row = ChannelArt(
                id=uuid7(),
                channel_id=channel_id,
                role=role,
                batch=batch,
                variant=variant,
                asset_id=asset.id,
                strategy_id=strategy.id,
            )
            db.add(row)
            rows.append(row)
    db.flush()
    return rows


def make_watermark(
    db: Session, data_dir: Path, channel_id: uuid.UUID, source_asset_id: uuid.UUID
) -> ChannelArt:
    """150 × 150 watermark from the owner's uploaded brand logo; it becomes the channel's watermark."""
    source = db.get_one(MediaAsset, source_asset_id)
    rights = usable(db, source)
    if rights is None or source.origin != "OWNER_UPLOAD" or rights.rights_basis != "OWNER_CREATED":
        raise ArtError(
            "The watermark can only be made from your own logo file, uploaded with its rights record."
        )
    progress.report(20, "Fitting your logo into 150 × 150")
    img = watermark(read_blob(data_dir, source))
    asset = add_asset(
        db,
        data_dir,
        png(img),
        mime_type="image/png",
        kind="IMAGE",
        origin="OWNER_UPLOAD",
        rights=Rights(
            basis="OWNER_CREATED",
            licence_name="Your own brand logo (resized by TubeForge)",
            commercial_use_allowed=True,
            lineage={
                "derived_from": str(source.id),
                "transform": "trim, fit 150×150, transparent",
                "renderer": RENDERER,
            },
        ),
        created_by=("SYSTEM", RENDERER),
        channel_id=channel_id,
        width=WATERMARK_SIZE,
        height=WATERMARK_SIZE,
    )
    db.execute(
        update(ChannelArt)
        .where(ChannelArt.channel_id == channel_id, ChannelArt.role == "WATERMARK")
        .values(chosen=False)
    )
    row = ChannelArt(
        id=uuid7(),
        channel_id=channel_id,
        role="WATERMARK",
        batch=_next_batch(db, channel_id, "WATERMARK"),
        variant=1,
        asset_id=asset.id,
        chosen=True,
    )
    db.add(row)
    db.flush()
    return row

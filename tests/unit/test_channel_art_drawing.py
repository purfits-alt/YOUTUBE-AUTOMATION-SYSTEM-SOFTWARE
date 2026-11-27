"""Channel art drawing rules (Phase 8 step A): sizes, circle-safe logo, banner safe area, contrast,
watermark (roadmap acceptance: sizes, safe-area bounds, contrast)."""

from __future__ import annotations

import io
import math

import pytest
from PIL import Image, ImageDraw
from tubeforge_media import channel_art as ca

from tubeforge.research.blueprint import contrast_ratio

PALETTES = [
    ["#0F172A", "#F8FAFC", "#22C55E", "#38BDF8"],  # dark navy + light
    ["#FDF6EC", "#2E7D32", "#F4A261", "#264653"],  # cream wellness
    ["#7A7A7A", "#8C8C8C", "#9E9E9E", "#B0B0B0"],  # all mid greys (no good pair in the palette)
    ["#FF0000", "#00FF00", "#0000FF", "#FFFF00"],  # loud primaries
]


def brand(
    palette: list[str], name: str = "Open Node AI", tagline: str = "Run open AI on your own PC"
) -> ca.Brand:
    blueprint = {"positioning": tagline, "brand": {"palette": [{"hex": h, "role": "x"} for h in palette]}}
    return ca.brand_from(blueprint, name, None)


@pytest.mark.parametrize("palette", PALETTES)
@pytest.mark.parametrize("variant", [1, 2, 3])
def test_logo_is_800_square_with_readable_text_inside_the_circle(palette: list[str], variant: int) -> None:
    drawn = ca.logo(brand(palette), variant)
    assert drawn.image.size == (800, 800)
    assert drawn.text_contrast >= ca.MIN_CONTRAST
    for x0, y0, x1, y1 in drawn.text_boxes:  # every corner of the text inside YouTube's circle crop
        for x, y in ((x0, y0), (x1, y0), (x0, y1), (x1, y1)):
            assert math.hypot(x - 400, y - 400) <= ca.LOGO_SAFE_RADIUS + 10


@pytest.mark.parametrize("palette", PALETTES)
@pytest.mark.parametrize("variant", [1, 2, 3])
def test_banner_text_stays_in_the_area_every_device_shows(palette: list[str], variant: int) -> None:
    drawn = ca.banner(
        brand(palette, tagline="A very long tagline that keeps going and going past the width"), variant
    )
    assert drawn.image.size == (2560, 1440)
    assert drawn.text_contrast >= ca.MIN_CONTRAST
    sx0, sy0, sx1, sy1 = ca.BANNER_SAFE
    assert (sx1 - sx0, sy1 - sy0) == (1546, 423)
    assert len(drawn.text_boxes) == 2
    for x0, y0, x1, y1 in drawn.text_boxes:
        assert sx0 <= x0 and x1 <= sx1 and sy0 <= y0 and y1 <= sy1, (x0, y0, x1, y1)
    # the actual pixels behind the name have the measured contrast
    x0, y0, x1, y1 = drawn.text_boxes[0]
    corner = "#{:02X}{:02X}{:02X}".format(*drawn.image.convert("RGB").getpixel((x0 - 2, (y0 + y1) // 2)))  # type: ignore[str-format]
    ink, _ = ca.text_colour(corner, prefer=brand(palette).light)
    assert contrast_ratio(ink, corner) >= ca.MIN_CONTRAST


def test_brand_picks_a_readable_pair_and_a_tagline() -> None:
    b = brand(["#7A7A7A", "#8C8C8C", "#9E9E9E", "#B0B0B0"])
    ink, ratio = ca.text_colour(b.dark, prefer=b.light)
    assert ratio >= ca.MIN_CONTRAST and ink in ("#FFFFFF", "#111111", b.light)
    long = {
        "positioning": "Practical guides to running open AI models on your own computer "
        "without any cloud costs."
    }
    assert ca.default_tagline(long) == "Practical guides to running open AI models on your own computer…"
    assert ca.default_tagline({"positioning": "Calm science. Second sentence."}) == "Calm science"
    assert [ca.initials(n) for n in ("Open Node AI", "PurfitsWellnessHub", "calm")] == ["ON", "PW", "C"]


def test_names_the_font_cannot_draw_are_refused_with_a_clear_reason() -> None:
    ca.check_drawable("Open Node AI", "Résumé — Ünïcode Привет")
    with pytest.raises(ca.ArtError, match="cannot draw"):
        ca.check_drawable("اردو کہانیاں")


def test_watermark_is_150_square_trimmed_and_transparent() -> None:
    src = Image.new("RGBA", (1200, 600), (0, 0, 0, 0))
    ImageDraw.Draw(src).rectangle((300, 200, 900, 400), fill=(200, 30, 60, 255))
    buf = io.BytesIO()
    src.save(buf, format="PNG")
    out = ca.watermark(buf.getvalue())
    assert out.size == (150, 150) and out.mode == "RGBA"
    assert out.getpixel((0, 0)) == (0, 0, 0, 0)  # transparent corner
    box = out.getchannel("A").getbbox()
    assert box is not None and box[2] - box[0] >= 130  # trimmed, then fitted to (almost) full width
    png = ca.png(out)
    assert png.startswith(b"\x89PNG") and len(png) < 1_000_000  # YouTube: ≤ 1 MB


def test_watermark_refuses_files_that_are_not_images() -> None:
    with pytest.raises(ca.ArtError, match="could not be read"):
        ca.watermark(b"\x89PNG\r\n\x1a\n not really a png")

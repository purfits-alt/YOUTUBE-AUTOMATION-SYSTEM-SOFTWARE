"""Procedural template registry v1 and scene keyframe renderer (VIDEO_PRODUCTION_SPEC §5, Phase 8 B).

16 templates. 12 are drawn by TubeForge itself (Pillow, the channel's brand palette, Source Sans Pro
OFL-1.1); 4 need the owner's own media or a public-domain map and arrive with uploads (step D). Each
template has a strict parameter model: A13 proposes parameters, code validates them, and anything
that does not fit falls back to ``kinetic_title`` so a scene always gets a picture.

Phase 8 draws one keyframe per scene (the picture the scene shows); motion (zooms, reveals, counters)
is added by the renderer in Phase 9 from the same template id and parameters.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Any

from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from tubeforge_media.channel_art import Brand, _mix, fit, font, text_colour

Text60 = Annotated[str, Field(min_length=1, max_length=60)]
Text80 = Annotated[str, Field(min_length=1, max_length=80)]
SIZES = {"LONG": (1920, 1080), "SHORT": (1080, 1920)}
MARGIN = 0.07


# ------------------------------------------------------------------------------- parameter models
class KineticTitle(BaseModel):
    text: Text80


class LowerThird(BaseModel):
    title: Text60
    subtitle: Annotated[str, Field(max_length=80)] = ""


class BulletReveal(BaseModel):
    title: Annotated[str, Field(max_length=60)] = ""
    items: Annotated[list[Text60], Field(min_length=2, max_length=5)]


class QuoteCard(BaseModel):
    quote: Annotated[str, Field(min_length=1, max_length=200)]
    attribution: Annotated[str, Field(max_length=60)] = ""


class Chart(BaseModel):
    title: Text60
    labels: Annotated[
        list[Annotated[str, Field(min_length=1, max_length=24)]], Field(min_length=2, max_length=6)
    ]
    values: Annotated[list[float], Field(min_length=2, max_length=6)]
    unit: Annotated[str, Field(max_length=8)] = ""

    @model_validator(mode="after")
    def _same_length(self) -> Chart:
        if len(self.labels) != len(self.values):
            raise ValueError("labels and values must have the same length")
        if any(v < 0 for v in self.values):
            raise ValueError("values must not be negative")
        return self


class PieChart(Chart):
    @field_validator("values")
    @classmethod
    def _positive(cls, v: list[float]) -> list[float]:
        if sum(v) <= 0:
            raise ValueError("values must add up to more than 0")
        return v


class NumberCounter(BaseModel):
    value: Annotated[str, Field(min_length=1, max_length=14)]
    label: Text60


class TimelineSteps(BaseModel):
    title: Annotated[str, Field(max_length=60)] = ""
    steps: Annotated[
        list[Annotated[str, Field(min_length=1, max_length=40)]], Field(min_length=2, max_length=6)
    ]


class SplitCompare(BaseModel):
    left_title: Annotated[str, Field(min_length=1, max_length=30)]
    left_items: Annotated[
        list[Annotated[str, Field(min_length=1, max_length=50)]], Field(min_length=1, max_length=4)
    ]
    right_title: Annotated[str, Field(min_length=1, max_length=30)]
    right_items: Annotated[
        list[Annotated[str, Field(min_length=1, max_length=50)]], Field(min_length=1, max_length=4)
    ]


class ProgressBar(BaseModel):
    label: Text60
    part: Annotated[int, Field(ge=1, le=50)]
    total: Annotated[int, Field(ge=1, le=50)]


class SoftReminder(BaseModel):
    text: Annotated[str, Field(min_length=1, max_length=90)]


class NeedsMedia(BaseModel):
    """Placeholder parameters of a template that needs the owner's media (step D)."""

    note: Annotated[str, Field(max_length=200)] = ""


@dataclass(frozen=True)
class Template:
    id: str
    label: str
    treatment: str  # TEMPLATE | CHART | KINETIC_TEXT | OWNER_MEDIA
    params: type[BaseModel]
    use_for: str  # one line for A13: when this template fits
    needs_media: bool = False


REGISTRY: dict[str, Template] = {
    t.id: t
    for t in (
        Template(
            "kinetic_title", "Big title", "KINETIC_TEXT", KineticTitle, "a short statement or the hook line"
        ),
        Template(
            "lower_third",
            "Name strip",
            "TEMPLATE",
            LowerThird,
            "naming a term, person or place under the narration",
        ),
        Template(
            "bullet_reveal", "Bullet points", "TEMPLATE", BulletReveal, "2–5 short points, tips or reasons"
        ),
        Template(
            "quote_card", "Quote", "TEMPLATE", QuoteCard, "a definition or a sentence worth reading on screen"
        ),
        Template("bar_chart", "Bar chart", "CHART", Chart, "comparing 2–6 numbers stated in the brief"),
        Template(
            "line_chart", "Line chart", "CHART", Chart, "a change over time with numbers from the brief"
        ),
        Template("pie_chart", "Pie chart", "CHART", PieChart, "parts of a whole with numbers from the brief"),
        Template(
            "number_counter", "Big number", "CHART", NumberCounter, "one striking number from the brief"
        ),
        Template("timeline_steps", "Steps", "TEMPLATE", TimelineSteps, "an order of steps or stages"),
        Template(
            "split_compare", "Compare", "TEMPLATE", SplitCompare, "two sides: before/after, myth/fact, A vs B"
        ),
        Template(
            "progress_bar", "Progress", "TEMPLATE", ProgressBar, "a section change: where we are in the video"
        ),
        Template(
            "subscribe_reminder_soft",
            "Soft reminder",
            "TEMPLATE",
            SoftReminder,
            "the call to action, once, near the end",
        ),
        Template(
            "ken_burns_photo", "Photo pan", "OWNER_MEDIA", NeedsMedia, "your own or licensed photo", True
        ),
        Template(
            "screen_recording_frame",
            "Screen recording",
            "OWNER_MEDIA",
            NeedsMedia,
            "your screen recording",
            True,
        ),
        Template("owner_cam_frame", "Your camera", "OWNER_MEDIA", NeedsMedia, "your own camera clip", True),
        Template(
            "map_highlight",
            "Map",
            "OWNER_MEDIA",
            NeedsMedia,
            "a public-domain map (needs the map file)",
            True,
        ),
    )
}
PROCEDURAL = [t.id for t in REGISTRY.values() if not t.needs_media]
FALLBACK = "kinetic_title"


def validate(template_id: str, params: dict[str, Any] | None) -> BaseModel | None:
    """The template's checked parameters, or None if the template or its parameters do not fit."""
    template = REGISTRY.get(template_id)
    if template is None or template.needs_media:
        return None
    try:
        return template.params.model_validate(params or {})
    except ValidationError:
        return None


# --------------------------------------------------------------------------------------- drawing
@dataclass(frozen=True)
class Frame:
    image: Image.Image
    text_boxes: list[tuple[int, int, int, int]]
    text_contrast: float


class _Canvas:
    def __init__(self, brand: Brand, size: tuple[int, int]) -> None:
        self.brand, self.w, self.h = brand, size[0], size[1]
        self.img = Image.new("RGB", size, brand.dark)
        self.d = ImageDraw.Draw(self.img)
        self.m = int(min(self.w, self.h) * MARGIN)
        self.ink, self.ratio = text_colour(brand.dark, prefer=brand.light)
        self.boxes: list[tuple[int, int, int, int]] = []
        self.vertical = self.h > self.w

    def text(self, xy: tuple[float, float], text: str, weight: str, max_w: int, max_h: int, start: int,
             anchor: str = "mm", fill: str | None = None) -> tuple[int, int, int, int]:  # fmt: skip
        f = fit(text, weight, max_w, max_h, start)
        self.d.text(xy, text, font=f, fill=fill or self.ink, anchor=anchor)
        box = self.d.textbbox(xy, text, font=f, anchor=anchor)
        out = (int(box[0]), int(box[1]), int(box[2]), int(box[3]))
        self.boxes.append(out)
        return out

    def paragraph(self, xy: tuple[float, float], text: str, weight: str, max_w: int, max_h: int, start: int,
                  align: str = "center", fill: str | None = None) -> tuple[int, int, int, int]:  # fmt: skip
        """Text wrapped over up to 4 lines, as large as fits the box; xy is the box's top-left
        (align left) or top-centre (align center)."""
        size = start
        while True:
            f = font(weight, size)
            lines = _wrap(text, f, max_w)
            line_h = int(size * 1.18)
            if (len(lines) <= 4 and line_h * len(lines) <= max_h) or size <= 14:
                break
            size = int(size * 0.92)
        x, y = xy
        top = y + (max_h - line_h * len(lines)) / 2
        boxes = []
        for i, line in enumerate(lines):
            anchor = "mt" if align == "center" else "lt"
            self.d.text((x, top + i * line_h), line, font=f, fill=fill or self.ink, anchor=anchor)
            boxes.append(self.d.textbbox((x, top + i * line_h), line, font=f, anchor=anchor))
        out = (
            int(min(b[0] for b in boxes)),
            int(min(b[1] for b in boxes)),
            int(max(b[2] for b in boxes)),
            int(max(b[3] for b in boxes)),
        )
        self.boxes.append(out)
        return out

    def frame(self) -> Frame:
        return Frame(self.img, self.boxes, self.ratio)


def _wrap(text: str, f: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
    lines: list[str] = []
    for word in text.split():
        trial = f"{lines[-1]} {word}" if lines else word
        if lines and f.getlength(trial) <= max_w:
            lines[-1] = trial
        else:
            lines.append(word)
    return lines or [""]


def _kinetic_title(c: _Canvas, p: KineticTitle) -> None:
    box = c.paragraph((c.w / 2, c.h * 0.22), p.text, "black", c.w - 2 * c.m, int(c.h * 0.5), 170)
    c.d.rectangle((c.w / 2 - 120, box[3] + 30, c.w / 2 + 120, box[3] + 46), fill=c.brand.accent)


def _lower_third(c: _Canvas, p: LowerThird) -> None:
    band_top = int(c.h * (0.70 if not c.vertical else 0.74))
    c.d.rectangle((0, band_top, c.w, c.h - c.m), fill=_mix(c.brand.dark, c.brand.accent, 0.12))
    c.d.rectangle((c.m, band_top + 24, c.m + 14, c.h - c.m - 24), fill=c.brand.accent)
    sub = 0.42 if p.subtitle else 0
    c.text(
        (c.m + 44, band_top + 24),
        p.title,
        "bold",
        c.w - 2 * c.m - 60,
        int((c.h - c.m - band_top) * 0.48),
        96,
        "lt",
    )
    if p.subtitle:
        c.text((c.m + 44, c.h - c.m - 24), p.subtitle, "regular", c.w - 2 * c.m - 60,
               int((c.h - c.m - band_top) * sub), 56, "lb")  # fmt: skip


def _list(c: _Canvas, title: str, items: list[str], numbered: bool) -> None:
    top = c.m
    if title:
        box = c.text((c.m, c.m), title, "bold", c.w - 2 * c.m, int(c.h * 0.14), 96, "lt")
        top = box[3] + 40
    row = (c.h - c.m - top) / max(len(items), 1)
    for i, item in enumerate(items):
        y = top + row * i + row / 2
        mark = f"{i + 1}" if numbered else ""
        r = min(34, int(row * 0.3))
        c.d.ellipse((c.m, y - r, c.m + 2 * r, y + r), fill=c.brand.accent)
        if mark:
            ink, _ = text_colour(c.brand.accent)
            c.d.text((c.m + r, y), mark, font=font("bold", int(r * 1.1)), fill=ink, anchor="mm")
        c.text((c.m + 2 * r + 30, y), item, "semibold", c.w - 3 * c.m - 2 * r, int(row * 0.6), 72, "lm")


def _bullet_reveal(c: _Canvas, p: BulletReveal) -> None:
    _list(c, p.title, p.items, numbered=False)


def _timeline_steps(c: _Canvas, p: TimelineSteps) -> None:
    _list(c, p.title, p.steps, numbered=True)


def _quote_card(c: _Canvas, p: QuoteCard) -> None:
    c.d.text((c.m, c.m - 20), "“", font=font("black", int(c.h * 0.22)), fill=c.brand.accent, anchor="lt")
    box = c.paragraph((c.w / 2, c.h * 0.22), p.quote, "semibold", c.w - 2 * c.m, int(c.h * 0.5), 110)
    if p.attribution:
        c.text(
            (c.w - c.m, box[3] + 50),
            f"— {p.attribution}",
            "regular",
            int(c.w * 0.6),
            int(c.h * 0.08),
            52,
            "rt",
        )


def _chart_frame(c: _Canvas, p: Chart) -> tuple[int, int, int, int]:
    title = c.text((c.m, c.m), p.title, "bold", c.w - 2 * c.m, int(c.h * 0.12), 84, "lt")
    return c.m, title[3] + 50, c.w - c.m, c.h - c.m - 70


def _value(v: float, unit: str) -> str:
    text = f"{v:,.0f}" if float(v).is_integer() else f"{v:,.1f}"
    return f"{text}{unit}"


def _bar_chart(c: _Canvas, p: Chart) -> None:
    x0, y0, x1, y1 = _chart_frame(c, p)
    top = max(p.values) or 1
    slot = (x1 - x0) / len(p.values)
    for i, (label, v) in enumerate(zip(p.labels, p.values, strict=True)):
        bx0, bx1 = x0 + slot * i + slot * 0.18, x0 + slot * (i + 1) - slot * 0.18
        by0 = y1 - (y1 - y0 - 60) * (v / top)
        c.d.rectangle(
            (bx0, by0, bx1, y1),
            fill=c.brand.accent if i % 2 == 0 else _mix(c.brand.accent, c.brand.light, 0.35),
        )
        c.text(((bx0 + bx1) / 2, by0 - 12), _value(v, p.unit), "bold", int(slot * 0.9), 56, 48, "mb")
        c.text(((bx0 + bx1) / 2, y1 + 16), label, "regular", int(slot * 0.95), 50, 40, "mt")


def _line_chart(c: _Canvas, p: Chart) -> None:
    x0, y0, x1, y1 = _chart_frame(c, p)
    top, low = max(p.values), min(p.values)
    span = (top - low) or 1
    step = (x1 - x0) / (len(p.values) - 1)
    points = [(x0 + step * i, y1 - (y1 - y0 - 70) * ((v - low) / span) - 10) for i, v in enumerate(p.values)]
    c.d.line([(x0, y1), (x1, y1)], fill=_mix(c.brand.dark, c.brand.light, 0.35), width=4)
    c.d.line(points, fill=c.brand.accent, width=10, joint="curve")
    for (x, y), label, v in zip(points, p.labels, p.values, strict=True):
        c.d.ellipse((x - 14, y - 14, x + 14, y + 14), fill=c.brand.accent)
        anchor_x = min(max(x, x0 + 60), x1 - 60)
        c.text((anchor_x, y - 26), _value(v, p.unit), "bold", int(step * 0.9), 50, 44, "mb")
        c.text((anchor_x, y1 + 16), label, "regular", int(step * 0.95), 46, 38, "mt")


def _pie_chart(c: _Canvas, p: Chart) -> None:
    x0, y0, x1, y1 = _chart_frame(c, p)
    total = sum(p.values) or 1
    r = min((x1 - x0) * (0.32 if not c.vertical else 0.45), (y1 - y0) / 2 - 10)
    cx, cy = (x0 + r + 10, (y0 + y1) / 2) if not c.vertical else ((x0 + x1) / 2, y0 + r + 10)
    extra = _mix(c.brand.accent, c.brand.light, 0.45)
    colours = list(dict.fromkeys([c.brand.accent, *(h for h in c.brand.palette if h != c.brand.dark), extra]))
    start = -90.0
    legend_x = cx + r + 80 if not c.vertical else x0
    legend_y = y0 + 30 if not c.vertical else cy + r + 60
    for i, (label, v) in enumerate(zip(p.labels, p.values, strict=True)):
        sweep = 360 * v / total
        colour = colours[i % len(colours)]
        if colour == c.brand.dark:
            colour = _mix(c.brand.dark, c.brand.light, 0.55)
        c.d.pieslice((cx - r, cy - r, cx + r, cy + r), start, start + sweep, fill=colour)
        start += sweep
        y = legend_y + i * 92
        c.d.rectangle((legend_x, y, legend_x + 50, y + 50), fill=colour)
        c.text(
            (legend_x + 74, y + 25),
            f"{label} · {_value(v, p.unit)}",
            "semibold",
            int(x1 - legend_x - 80),
            60,
            48,
            "lm",
        )


def _number_counter(c: _Canvas, p: NumberCounter) -> None:
    box = c.text(
        (c.w / 2, c.h * 0.44), p.value, "black", c.w - 2 * c.m, int(c.h * 0.34), 320, fill=c.brand.accent
    )
    c.text((c.w / 2, box[3] + 50), p.label, "semibold", c.w - 2 * c.m, int(c.h * 0.12), 80, "mt")


def _split_compare(c: _Canvas, p: SplitCompare) -> None:
    half = c.w / 2 if not c.vertical else c.h / 2
    panes = ((p.left_title, p.left_items, 0), (p.right_title, p.right_items, 1))
    for title, items, i in panes:
        box: tuple[float, float, float, float] = (
            (0, half * i, c.w, half * (i + 1)) if c.vertical else (half * i, 0, half * (i + 1), c.h)
        )
        tint = _mix(c.brand.dark, c.brand.accent, 0.10 if i == 0 else 0.22)
        c.d.rectangle(box, fill=tint)
        bx0, by0, bx1, by1 = (int(v) for v in box)
        head = c.text(
            (bx0 + c.m, by0 + c.m), title, "black", bx1 - bx0 - 2 * c.m, int((by1 - by0) * 0.16), 96, "lt"
        )
        row = (by1 - c.m - head[3] - 30) / len(items)
        for j, item in enumerate(items):
            c.paragraph((bx0 + c.m, head[3] + 30 + row * j), f"• {item}", "semibold",
                        bx1 - bx0 - 2 * c.m, int(row * 0.9), 76, "left")  # fmt: skip
    if c.vertical:
        c.d.rectangle((0, half - 6, c.w, half + 6), fill=c.brand.accent)
    else:
        c.d.rectangle((half - 6, 0, half + 6, c.h), fill=c.brand.accent)


def _progress_bar(c: _Canvas, p: ProgressBar) -> None:
    total = max(p.total, p.part)
    box = c.text((c.w / 2, c.h * 0.40), p.label, "black", c.w - 2 * c.m, int(c.h * 0.22), 150)
    y = box[3] + 80
    c.d.rounded_rectangle((c.m, y, c.w - c.m, y + 36), radius=18, fill=_mix(c.brand.dark, c.brand.light, 0.2))
    c.d.rounded_rectangle(
        (c.m, y, c.m + (c.w - 2 * c.m) * p.part / total, y + 36), radius=18, fill=c.brand.accent
    )
    c.text((c.w / 2, y + 70), f"{p.part} / {total}", "semibold", int(c.w * 0.4), 60, 52, "mt")


def _soft_reminder(c: _Canvas, p: SoftReminder) -> None:
    c.paragraph((c.w / 2, c.h * 0.25), p.text, "semibold", c.w - 2 * c.m, int(c.h * 0.5), 110)


DRAW: dict[str, Callable[[_Canvas, Any], None]] = {
    "kinetic_title": _kinetic_title,
    "lower_third": _lower_third,
    "bullet_reveal": _bullet_reveal,
    "quote_card": _quote_card,
    "bar_chart": _bar_chart,
    "line_chart": _line_chart,
    "pie_chart": _pie_chart,
    "number_counter": _number_counter,
    "timeline_steps": _timeline_steps,
    "split_compare": _split_compare,
    "progress_bar": _progress_bar,
    "subscribe_reminder_soft": _soft_reminder,
}
assert set(DRAW) == set(PROCEDURAL)


def render(template_id: str, params: BaseModel, brand: Brand, fmt: str = "LONG") -> Frame:
    """One keyframe for a scene: 1920×1080 (long-form) or 1080×1920 (Short)."""
    canvas = _Canvas(brand, SIZES.get(fmt, SIZES["LONG"]))
    DRAW[template_id](canvas, params)
    return canvas.frame()


def describe() -> list[dict[str, Any]]:
    """The registry as A13 sees it (procedural templates only; media templates arrive with uploads)."""
    return [
        {"id": t.id, "use_for": t.use_for, "params": t.params.model_json_schema()["properties"]}
        for t in REGISTRY.values()
        if not t.needs_media
    ]

"""Procedural template registry v1 and scene keyframes (VIDEO_PRODUCTION_SPEC §5, Phase 8 step B)."""

from __future__ import annotations

from typing import Any

import pytest
from tubeforge_media import channel_art as ca
from tubeforge_media import templates as tpl

PARAMS: dict[str, dict[str, Any]] = {
    "kinetic_title": {"text": "What a late dinner does to deep sleep"},
    "lower_third": {"title": "Heart rate variability", "subtitle": "the time between heartbeats"},
    "bullet_reveal": {"title": "Before bed", "items": ["Dim the lights", "Slow breathing"]},
    "quote_card": {"quote": "Slow-wave sleep is essential for brain recovery.", "attribution": "Wikipedia"},
    "bar_chart": {"title": "Resting heart rate", "labels": ["Awake", "Asleep"], "values": [70, 45]},
    "line_chart": {"title": "Overnight", "labels": ["10pm", "2am", "6am"], "values": [68, 46, 52]},
    "pie_chart": {"title": "Stages", "labels": ["Light", "Deep", "REM"], "values": [50, 25, 25], "unit": "%"},
    "number_counter": {"value": "40–50", "label": "beats per minute during sleep"},
    "timeline_steps": {"title": "Stages", "steps": ["Light sleep", "Deep sleep", "REM"]},
    "split_compare": {
        "left_title": "Belief",
        "left_items": ["Late meals ruin sleep"],
        "right_title": "Evidence",
        "right_items": ["An open question"],
    },
    "progress_bar": {"label": "Part 2", "part": 2, "total": 5},
    "subscribe_reminder_soft": {"text": "If this helped, subscribing helps the channel."},
}
PALETTES = [
    ["#FDF6EC", "#2E7D32", "#F4A261", "#264653"],
    ["#7A7A7A", "#8C8C8C", "#9E9E9E", "#B0B0B0"],
]


def brand(palette: list[str]) -> ca.Brand:
    return ca.brand_from(
        {"brand": {"palette": [{"hex": h, "role": "x"} for h in palette]}}, "Calm Science", "x"
    )


def test_registry_has_16_templates_12_drawn_by_tubeforge() -> None:
    assert len(tpl.REGISTRY) == 16 and sorted(tpl.PROCEDURAL) == sorted(PARAMS)
    assert {t.id for t in tpl.REGISTRY.values() if t.needs_media} == {
        "ken_burns_photo", "screen_recording_frame", "owner_cam_frame", "map_highlight",
    }  # fmt: skip
    seen = {d["id"] for d in tpl.describe()}
    assert seen == set(PARAMS) and all(d["use_for"] and d["params"] for d in tpl.describe())


@pytest.mark.parametrize("fmt", ["LONG", "SHORT"])
@pytest.mark.parametrize("palette", PALETTES)
@pytest.mark.parametrize("template_id", sorted(PARAMS))
def test_every_template_draws_a_readable_keyframe(template_id: str, palette: list[str], fmt: str) -> None:
    params = tpl.validate(template_id, PARAMS[template_id])
    assert params is not None
    frame = tpl.render(template_id, params, brand(palette), fmt)
    w, h = tpl.SIZES[fmt]
    assert frame.image.size == (w, h)
    assert frame.text_contrast >= ca.MIN_CONTRAST
    assert frame.text_boxes
    for x0, y0, x1, y1 in frame.text_boxes:  # no text runs off the picture
        assert 0 <= x0 <= x1 <= w and 0 <= y0 <= y1 <= h, (template_id, (x0, y0, x1, y1))


@pytest.mark.parametrize(
    ("template_id", "params"),
    [
        ("bar_chart", {"title": "x", "labels": ["a", "b"], "values": [1]}),  # lengths differ
        ("bar_chart", {"title": "x", "labels": ["a", "b"], "values": [1, -2]}),  # negative
        ("pie_chart", {"title": "x", "labels": ["a", "b"], "values": [0, 0]}),
        ("bullet_reveal", {"items": ["only one"]}),
        ("kinetic_title", {"text": "x" * 81}),
        ("ken_burns_photo", {}),  # needs the owner's media
        ("not_a_template", {"text": "x"}),
    ],
)
def test_bad_parameters_are_refused(template_id: str, params: dict[str, Any]) -> None:
    assert tpl.validate(template_id, params) is None

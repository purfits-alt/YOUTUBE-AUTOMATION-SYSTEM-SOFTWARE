"""Storyboard cutting and scene-visual rules, checked in code (Phase 8 step B, AGENT_PROMPTS A12/A13)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from tubeforge_agents import storyboard as sb
from tubeforge_media import templates as tpl

from tests.unit import content_fixtures as fx
from tubeforge.content import craft

BODY: dict[str, Any] = {
    "hook": {"text": "Your heart slows down at night. A late dinner can change that. Here is how much."},
    "sections": [
        {"heading": "Sleep", "text": "Deep sleep is when the body recovers. It mostly happens early on."},
        {"heading": "Meals", "text": "Here's where it got weird. Digestion keeps the body busy for hours."},
    ],
    "payoff": "So the timing of a meal matters more than its size.",
    "cta": "Try an earlier dinner for a week and see how you feel.",
    "re_hooks": [{"at_pct": 50, "technique": "TWIST", "text": "Here's where it got weird."}],
}


def test_sentences_keep_every_spoken_word_in_order_and_mark_the_hook() -> None:
    sents = sb.sentences(BODY)
    assert [s.id for s in sents] == [f"s{i}" for i in range(len(sents))]
    assert [s.text for s in sents if s.hook] == [
        "Your heart slows down at night.", "A late dinner can change that.", "Here is how much.",
    ]  # fmt: skip
    joined = " ".join(s.text for s in sents)
    assert craft.words(joined) == craft.measure(BODY)[0]
    # [[OWNER: …]] prompts are never narration (owner decision 2026-11-27).
    long = sb.sentences(fx.long_script())
    assert not any("OWNER" in s.text for s in long)


def test_a_cut_must_use_every_sentence_once_in_order() -> None:
    sents = sb.sentences(BODY)
    last = f"s{len(sents) - 1}"
    ok, _ = sb.check_cut([{"first": "s0", "last": "s2"}, {"first": "s3", "last": last}], sents)
    assert ok is not None and [(c.first, c.last) for c in ok] == [(0, 2), (3, len(sents) - 1)]
    for bad, why in [
        ([{"first": "s0", "last": "s2"}, {"first": "s4", "last": last}], "must start at s3"),
        ([{"first": "s0", "last": "s2"}, {"first": "s2", "last": last}], "must start at s3"),
        ([{"first": "s0", "last": "s2"}], "are in no scene"),
        ([{"first": "s0", "last": "s99"}], "does not exist"),
    ]:
        cuts, reason = sb.check_cut(bad, sents)
        assert cuts is None and why in reason


def test_scene_one_is_exactly_the_hook() -> None:
    sents = sb.sentences(BODY)
    n = len(sents)
    # The model put the hook and the first section together, and split the hook elsewhere: fixed.
    cuts, _ = sb.check_cut(
        [{"first": "s0", "last": "s1", "visual_instruction": "Big title", "style": "kinetic_text"},
         {"first": "s2", "last": "s4", "visual_instruction": "Chart", "style": "chart"},
         {"first": "s5", "last": f"s{n - 1}", "visual_instruction": "End", "style": "kinetic_text"}],
        sents,
    )  # fmt: skip
    assert cuts is not None
    fixed = sb.with_hook_scene(cuts, sents)
    assert [(c.first, c.last) for c in fixed] == [(0, 2), (3, 4), (5, n - 1)]
    assert fixed[0].visual_instruction == "Big title" and fixed[1].visual_instruction == "Chart"


def test_code_cut_never_crosses_a_part_and_marks_rehooks() -> None:
    sents = sb.sentences(BODY)
    cuts = sb.auto_cut(sents, "LONG", 150)
    assert (cuts[0].first, cuts[0].last) == (0, 2)  # the hook
    for c in cuts:
        assert len({s.part for s in sents[c.first : c.last + 1]}) == 1
    assert [c.first for c in cuts] == [0, 3, 5, 7, 8]
    sb.mark_rehooks(cuts, sents, ["Here's where it got weird."])
    assert [c.pattern_interrupt for c in cuts] == [False, False, True, False, False]
    assert sb.seconds("one two three", 150) == Decimal("1.2")
    assert sb.seconds("", 150) == Decimal("0.5")  # never zero


def scene(position: int, narration: str = "Deep sleep is when the body recovers.", **kw: Any) -> Any:
    from tubeforge.db.models import Scene

    return Scene(
        position=position, narration=narration, visual_instruction="", on_screen_text=kw.pop("text", None),
        is_hook=position == 1, pattern_interrupt=kw.pop("interrupt", False), **kw,
    )  # fmt: skip


CLAIMS = {"c1": "Resting heart rate falls to 40–50 beats per minute in sleep.", "c2": "About 1,500 people."}


@pytest.mark.parametrize(
    ("proposal", "kept", "why"),
    [
        ({"template_id": "bar_chart", "params": {"title": "Heart rate", "labels": ["Low", "High"],
          "values": [40, 50]}, "chart_claim_ids": ["c1"]}, "bar_chart", ""),
        ({"template_id": "number_counter", "params": {"value": "1,500", "label": "people"},
          "chart_claim_ids": ["c2"]}, "number_counter", ""),
        ({"template_id": "bar_chart", "params": {"title": "Heart rate", "labels": ["Low", "High"],
          "values": [40, 60]}, "chart_claim_ids": ["c1"]}, "lower_third", "not in the cited"),
        ({"template_id": "number_counter", "params": {"value": "45", "label": "bpm"}}, "lower_third",
         "not in the cited"),
        ({"template_id": "ken_burns_photo", "params": {}}, "lower_third", "needs your own media"),
        ({"template_id": "made_up", "params": {}}, "lower_third", "not in the template registry"),
        ({"template_id": "kinetic_title", "params": {"text": "x" * 200}}, "lower_third", "did not fit"),
        ({"template_id": "kinetic_title", "params": {"text": "Guaranteed results in 7 days"}}, "lower_third",
         "promise"),
        ({"template_id": "subscribe_reminder_soft", "params": {"text": "Subscribe if this helped."}},
         "lower_third", "at the end"),
        (None, "lower_third", "no template"),
    ],
)  # fmt: skip
def test_a13_choices_are_kept_only_when_every_rule_holds(
    proposal: dict[str, Any] | None, kept: str, why: str
) -> None:
    choice = sb.choose(proposal, scene(3), last=False, claims=CLAIMS)
    assert choice.template_id == kept and why in choice.why
    assert tpl.validate(choice.template_id, choice.params.model_dump()) is not None
    if kept in sb.CHARTS:
        assert choice.chart_claim_ids


def test_variety_rules_are_enforced_in_code() -> None:
    scenes = [scene(i, f"Sentence number {i} about sleep.", interrupt=i == 6) for i in range(1, 11)]
    same = [sb.Choice("lower_third", sb.text_params("lower_third", s)) for s in scenes]
    sb.rebalance(same, scenes, [])
    ids = [c.template_id for c in same]
    assert max(ids.count(t) for t in set(ids)) <= 4  # ≤ 40 % of 10 scenes
    assert ids[0] in sb.BOLD_OPENERS  # the hook
    assert ids[5] != ids[4]  # the pattern interrupt changes the picture
    # The opening differs from a recent video's opening.
    recent = [[*ids[:5], "x"]]
    again = [sb.Choice(t, sb.text_params(t, s)) for t, s in zip(ids, scenes, strict=True)]
    sb.rebalance(again, scenes, recent)
    assert [c.template_id for c in again[:5]] != ids[:5]


def test_numbers_are_read_the_way_people_write_them() -> None:
    assert sb.numbers("40–50 beats, 1,500 people, 7.5 hours, 3,5 %") == {40, 50, 1500, 7.5, 3.5}

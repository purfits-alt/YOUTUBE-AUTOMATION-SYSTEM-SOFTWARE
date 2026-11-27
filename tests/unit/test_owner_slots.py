"""Owner report and decision 2026-11-27: [[OWNER: …]] prompts reached the storyboard unfilled, and the
owner's own words are optional. Empty places become suggestions; nothing like "OWNER: …" is spoken."""

from __future__ import annotations

from tubeforge.content import craft, scripts

# From the PurfitsWellnessHub script the owner shared (shortened).
SECTION = (
    "The US National Sleep Foundation recommends that adults target at least 7 hours of sleep per night. "
    "[[OWNER: Share your experience tracking deep sleep or how you notice mental clarity after a solid "
    "night of slow-wave sleep.]] When slow-wave sleep is curtailed or fragmented, cognitive functions can "
    "take a hit."
)


def body() -> dict[str, object]:
    return {
        "hook": {"text": "During sleep, your resting heart rate drops."},
        "promise_delivery": {"text": "Here is what a late dinner does."},
        "sections": [
            {"heading": "Deep sleep", "text": SECTION, "fact_refs": []},
            {"heading": "Meals", "text": "Digestion raises activity. [[OWNER: Your evening meal timing.]]"},
        ],
        "payoff": "An open question.",
        "cta": "Try a calmer wind-down. [[OWNER: what worked for you]]",
        "owner_slots": [{"section_index": 1, "prompt": "Your evening meal timing."}],
    }


def test_open_slots_are_listed_with_their_place_and_prompt() -> None:
    slots = scripts.open_owner_slots(body())
    assert [(s["field"], s["prompt"]) for s in slots] == [
        ("sections.0", "Share your experience tracking deep sleep or how you notice mental clarity after a "
         "solid night of slow-wave sleep."),
        ("sections.1", "Your evening meal timing."),
        ("cta", "what worked for you"),
    ]  # fmt: skip
    assert all(s["marker"] in craft.plain_text(body()) for s in slots)


def test_lifting_keeps_the_script_complete_and_the_prompts_as_suggestions() -> None:
    lifted = scripts.lift_owner_slots(body())
    assert scripts.open_owner_slots(lifted) == []
    assert "OWNER" not in craft.plain_text(lifted)
    assert lifted["sections"][0]["text"] == (  # type: ignore[index]
        "The US National Sleep Foundation recommends that adults target at least 7 hours of sleep per night. "
        "When slow-wave sleep is curtailed or fragmented, cognitive functions can take a hit."
    )
    assert lifted["cta"] == "Try a calmer wind-down."
    # Prompts kept once each, beside the place they came from (the CTA counts as the last section).
    assert [(s["section_index"], s["prompt"][:24]) for s in lifted["owner_slots"]] == [  # type: ignore[index, union-attr]
        (1, "Your evening meal timing"),
        (0, "Share your experience tr"),
        (1, "what worked for you"),
    ]
    # Craft still sees the owner's optional places (≥ 2 for long-form) and the input is unchanged.
    findings = craft.check_script(lifted, fmt="LONG", target_duration_s=480)
    assert not [f for f in findings if f.code == "OWNER_SLOTS"]
    assert "[[OWNER:" in str(body()["sections"])

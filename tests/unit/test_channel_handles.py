"""YouTube @handle suggestions (owner request 2026-11-15): valid, distinct, never checked online."""

from __future__ import annotations

import pytest

from tubeforge.channel_handles import is_valid_handle, suggest_handles


def test_suggestions_for_a_normal_name() -> None:
    out = suggest_handles("Open Node AI")
    assert out[0] == "@OpenNodeAI"
    assert "@Open_Node_AI" in out and "@TheOpenNodeAI" in out
    assert len(out) == len({h.lower() for h in out}) <= 6
    assert all(is_valid_handle(h) and 3 <= len(h) - 1 <= 30 for h in out)
    assert "@Open.Node.AI" not in out  # looks like a web address (".AI")


@pytest.mark.parametrize(
    ("handle", "ok"),
    [
        ("@BudgetLab", True), ("Budget_Lab", True), ("@Budget.Lab", True), ("@ab", False),
        ("@_Budget", False), ("@Budget-", False), ("@Budget..Lab", False), ("@my.channel.com", False),
        ("@" + "a" * 31, False), ("@Budget Lab", False),
    ],
)  # fmt: skip
def test_handle_rules(handle: str, ok: bool) -> None:
    assert is_valid_handle(handle) is ok


def test_long_names_keep_whole_words_and_odd_names_fall_back() -> None:
    long = suggest_handles("A very long channel name that goes on and on forever")
    assert long and all(len(h) - 1 <= 30 for h in long) and long[0] == "@AVeryLongChannelNameThat"
    assert suggest_handles("طالب علم بجٹ", "Student budgets")[0] == "@StudentBudgets"  # non-Latin name
    assert suggest_handles("!!") == []

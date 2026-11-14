"""Phase 7 core: script craft validators (golden set), similarity service (ADR-0029), value-add score."""

# ruff: noqa: E501  (table-style test cases)
from __future__ import annotations

import hashlib
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest

from tests.unit import content_fixtures as fx
from tubeforge.content import craft, scripts, similarity, value_add


def codes(script: dict[str, Any], fmt: craft.Format = "LONG", target: int = 480, **kw: Any) -> list[str]:
    return [f.code for f in craft.check_script(script, fmt=fmt, target_duration_s=target, **kw)]


# ------------------------------------------------------------------------- craft: golden set (15)
def test_good_long_and_short_scripts_pass() -> None:
    assert codes(fx.long_script(), claim_ids={"c1"}) == []
    assert codes(fx.short_script(), fmt="SHORT", target=45, claim_ids={"c1"}) == []


def _with_hook(text: str) -> dict[str, Any]:
    s = fx.long_script()
    s["hook"] = {**s["hook"], "text": text}
    return s


@pytest.mark.parametrize(
    ("name", "script", "fmt", "target", "expected"),
    [
        ("hook too short", _with_hook("Three leaks drain your money."), "LONG", 480, "HOOK_LENGTH"),
        ("hook too long", _with_hook(" ".join(["word"] * 60)), "LONG", 480, "HOOK_LENGTH"),
        ("greeting first", _with_hook("Hey guys, " + fx.long_script()["hook"]["text"]), "LONG", 480, "HOOK_GREETING"),
        (
            "promise late",
            fx.mutate(fx.long_script(), promise_delivery={"promise_statement": "x", "delivered_at_s": 22, "text": "x"}),
            "LONG", 480, "PROMISE_LATE",
        ),
        (
            "short promise late",
            fx.mutate(fx.short_script(), promise_delivery={"promise_statement": "x", "delivered_at_s": 4, "text": "x"}),
            "SHORT", 45, "PROMISE_LATE",
        ),
        ("promise missing", fx.mutate(fx.long_script(), promise_delivery={}), "LONG", 480, "PROMISE_MISSING"),
        (
            "re-hook band missing",
            fx.mutate(fx.long_script(), re_hooks=[{"at_pct": 25, "technique": "TWIST", "text": "x"}]),
            "LONG", 480, "REHOOK_MISSING",
        ),
        (
            "open loop never closed",
            fx.mutate(fx.long_script(), open_loops=[{"id": "L1", "opened_in_section": 2, "closed_in_section": 1, "text": "x"}]),
            "LONG", 480, "OPEN_LOOP_UNCLOSED",
        ),
        ("AI filler", fx.mutate(fx.long_script(), cta="Let's dive in and tell me which leak."), "LONG", 480, "BANNED_PHRASE"),
        ("forbidden promise", fx.mutate(fx.long_script(), payoff="This method is guaranteed to work."), "LONG", 480, "FORBIDDEN_PROMISE"),
        ("duration off", fx.long_script(minutes=4), "LONG", 480, "DURATION"),
        (
            "owner slots missing",
            fx.mutate(fx.short_script(), owner_slots=[], sections=[{"heading": "x", "text": "No slot here at all today.", "fact_refs": []}]),
            "SHORT", 10, "OWNER_SLOTS",
        ),
        ("short hook too long", _with_hook("x"), "SHORT", 45, "HOOK_LENGTH"),
    ],
)  # fmt: skip
def test_craft_failures_are_caught(
    name: str, script: dict[str, Any], fmt: craft.Format, target: int, expected: str
) -> None:
    if name == "short hook too long":
        script = fx.short_script()
        script["hook"]["text"] = (
            "This is a very long opening line that goes on and on for a Short video today"
        )
    assert expected in codes(script, fmt=fmt, target=target), name


def test_recent_phrases_and_unknown_claims_are_flagged() -> None:
    s = fx.long_script()
    assert "BANNED_PHRASE" in codes(s, recent_phrases=("three categories did almost all the damage",))
    assert "FACT_REF_UNKNOWN" in codes(s, claim_ids={"c9"})


def test_short_over_180_seconds_and_sparse_rehooks() -> None:
    long_short = fx.short_script()
    long_short["sections"][0]["text"] = " ".join(["word"] * 500)
    assert "SHORT_TOO_LONG" in codes(long_short, fmt="SHORT", target=200)
    twelve = fx.long_script(minutes=12)
    assert "REHOOK_SPARSE" in codes(twelve, target=720)  # 25/50/75 % of 12 min leaves 180 s gaps
    findings = craft.check_script(twelve, fmt="LONG", target_duration_s=720)
    assert all(f.severity == "WARNING" for f in findings if f.code == "REHOOK_SPARSE")
    assert craft.errors(findings) == []


def test_duration_is_measured_from_the_words_not_the_model() -> None:
    s = fx.long_script()
    s["est_duration_s"] = 30  # the model's own number is ignored
    words, est = craft.measure(s)
    assert abs(est - 480) <= 48 and words == sum(craft.words(p) for p in craft.spoken_parts(s))
    assert craft.seconds(150) == 60.0 and craft.seconds(150, wpm=100) == 90.0


# ---------------------------------------------------------------------------- script versions
def test_fingerprint_is_stable_and_diff_shows_changes() -> None:
    a = fx.long_script()
    b = fx.long_script()
    assert scripts.fingerprint(a) == scripts.fingerprint(b)
    b["sections"][0]["text"] = "A brand new opening for the first section."
    assert scripts.fingerprint(a) != scripts.fingerprint(b)
    lines = scripts.diff(a, b, "v1", "v2")
    assert lines[0] == "--- v1" and any(line.startswith("+A brand new opening") for line in lines)
    summary = scripts.summary(a)
    assert summary["word_count"] > 1000 and len(summary["content_sha256"]) == 64
    assert "[[OWNER:" in summary["plain_text"]


# --------------------------------------------------------------------------------- value add
def test_value_add_score() -> None:
    assert value_add.score({}) == Decimal("0.00")
    assert value_add.score({"own_opinion": "short"}) == 0  # under 30 characters does not count
    full = {k: "x" * 40 for k in value_add.TEXT_FIELDS} | {"owner_footage": True, "owner_photos": True}
    assert value_add.score(full) == Decimal("100.00")
    assert value_add.score({"own_experience": "I tracked every purchase for thirty days."}) == 25
    assert value_add.filled_fields({"own_data": "x" * 30, "owner_photos": True}) == [
        "own_data",
        "owner_photos",
    ]


# -------------------------------------------------------------------------------- similarity
def test_trigram_fallback_scores() -> None:
    t = similarity.TrigramSimilarity()
    assert t.against("How I budget", ["How I budget", "Roman aqueducts"]) == [1.0, 0.0]
    m = t.pairwise(["a b c", "a b c", "zzz"])
    assert m[0][1] == 1.0 and m[0][2] == 0.0


class FakeEncoder:
    """Vectors by first word: same first word → same direction."""

    def encode(self, texts: list[str]) -> list[list[float]]:
        table = {"budget": [1.0, 0.0, 0.0], "money": [0.9, 0.1, 0.0], "chess": [0.0, 1.0, 0.0]}
        return [table.get(t.split()[0].lower(), [0.0, 0.0, 1.0]) for t in texts]


def test_embedding_similarity_and_helpers() -> None:
    sim = similarity.EmbeddingSimilarity(FakeEncoder())
    assert sim.method == "model2vec"
    scores = sim.against("budget tips", ["budget plan", "money saving", "chess openings"])
    assert scores[0] == 1.0 and 0.98 < scores[1] < 1.0 and scores[2] == 0.0
    near = similarity.nearest("money ideas", ["chess club", "budget week"], sim)
    assert near.index == 1 and near.score > similarity.IDEA_DUPLICATE
    assert similarity.nearest("x", [], sim) == similarity.Nearest(0.0, None)
    pairs = similarity.too_similar_pairs(["budget a", "budget b", "chess c"], sim=sim)
    assert pairs == [(0, 1, 1.0)]


def test_without_the_model_the_fallback_is_used(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(similarity, "model_dir", lambda: tmp_path / "missing")
    similarity.reset_similarity()
    try:
        assert similarity.get_similarity().method == "trigram"
        assert next(label for label, _ in similarity.self_test()) == "same"
    finally:
        similarity.reset_similarity()


def _fake_files(monkeypatch: pytest.MonkeyPatch) -> dict[str, bytes]:
    blobs = {"config.json": b"{}", "model.safetensors": b"weights" * 10}
    monkeypatch.setattr(
        similarity,
        "MODEL_FILES",
        {
            "config.json": (len(blobs["config.json"]), None),
            "model.safetensors": (
                len(blobs["model.safetensors"]),
                hashlib.sha256(blobs["model.safetensors"]).hexdigest(),
            ),
        },
    )
    return blobs


def test_fetch_model_checks_hosts_sizes_and_checksums(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    blobs = _fake_files(monkeypatch)
    seen: list[str] = []

    def ok(req: httpx.Request) -> httpx.Response:
        seen.append(req.url.host)
        name = req.url.path.rsplit("/", 1)[-1]
        if req.url.host == "huggingface.co" and name == "model.safetensors":  # large file → CDN
            return httpx.Response(
                302, headers={"location": "https://us.aws.cdn.hf.co/blob/model.safetensors"}
            )
        return httpx.Response(200, content=blobs[name])

    hooks = {"request": [similarity._check_download_host]}
    with httpx.Client(transport=httpx.MockTransport(ok), follow_redirects=True, event_hooks=hooks) as c:
        dest = similarity.fetch_model(tmp_path / "m", client=c)
    assert similarity.model_installed(dest) and "us.aws.cdn.hf.co" in seen
    with httpx.Client(transport=httpx.MockTransport(ok), follow_redirects=True, event_hooks=hooks) as c:
        seen.clear()
        similarity.fetch_model(tmp_path / "m", client=c)  # already correct: nothing downloaded
    assert seen == []

    def corrupt(req: httpx.Request) -> httpx.Response:
        name = req.url.path.rsplit("/", 1)[-1]
        data = blobs[name] if name == "config.json" else b"x" * len(blobs[name])
        return httpx.Response(200, content=data)

    with (
        pytest.raises(ValueError, match="checksum"),
        httpx.Client(transport=httpx.MockTransport(corrupt)) as c,
    ):
        similarity.fetch_model(tmp_path / "bad", client=c)
    assert not (tmp_path / "bad" / "model.safetensors").exists()

    def evil(req: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "https://evil.example.com/x"})

    with (
        pytest.raises(ValueError, match="Refusing"),
        httpx.Client(transport=httpx.MockTransport(evil), follow_redirects=True, event_hooks=hooks) as c,
    ):
        similarity.fetch_model(tmp_path / "evil", client=c)
    similarity.reset_similarity()

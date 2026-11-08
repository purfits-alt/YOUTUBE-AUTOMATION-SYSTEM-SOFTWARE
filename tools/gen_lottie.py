"""Generate TubeForge's own Lottie animations (original artwork, MIT like the repo).

Run: uv run python tools/gen_lottie.py  -> apps/web/src/assets/lottie/*.json
Kept as code so the animations are reviewable and reproducible (no third-party assets).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

OUT = Path(__file__).resolve().parent.parent / "apps" / "web" / "src" / "assets" / "lottie"
VIOLET = [0.486, 0.361, 1.0, 1]
CORAL = [1.0, 0.373, 0.427, 1]
WHITE = [1, 1, 1, 1]
EASE = {"i": {"x": [0.4], "y": [1]}, "o": {"x": [0.6], "y": [0]}}

J = dict[str, Any]


def static(v: Any) -> J:
    return {"a": 0, "k": v}


def anim(*frames: tuple[int, list[float]]) -> J:
    keys: list[J] = []
    for idx, (t, v) in enumerate(frames):
        k: J = {"t": t, "s": v}
        if idx < len(frames) - 1:
            k.update(EASE)
        keys.append(k)
    return {"a": 1, "k": keys}


def transform(p: list[float], s: J | None = None, o: J | None = None, r: J | None = None) -> J:
    return {
        "o": o or static(100),
        "r": r or static(0),
        "p": static([*p, 0]),
        "a": static([0, 0, 0]),
        "s": s or static([100, 100, 100]),
    }


def group(*items: J) -> J:
    tr = {
        "ty": "tr",
        "p": static([0, 0]),
        "a": static([0, 0]),
        "s": static([100, 100]),
        "r": static(0),
        "o": static(100),
    }
    return {"ty": "gr", "it": [*items, tr]}


def ellipse(size: float) -> J:
    return {"ty": "el", "p": static([0, 0]), "s": static([size, size])}


def rect(w: float, h: float, r: float) -> J:
    return {"ty": "rc", "p": static([0, 0]), "s": static([w, h]), "r": static(r)}


def fill(c: list[float], o: float = 100) -> J:
    return {"ty": "fl", "c": static(c), "o": static(o), "r": 1}


def stroke(c: list[float], w: float) -> J:
    return {"ty": "st", "c": static(c), "o": static(100), "w": static(w), "lc": 2, "lj": 2}


def path(points: list[list[float]], closed: bool = False) -> J:
    zero = [[0, 0] for _ in points]
    return {"ty": "sh", "ks": static({"i": zero, "o": zero, "v": points, "c": closed})}


def layer(ind: int, name: str, ks: J, shapes: list[J], op: int) -> J:
    return {
        "ty": 4,
        "ind": ind,
        "nm": name,
        "ip": 0,
        "op": op,
        "st": 0,
        "sr": 1,
        "ks": ks,
        "shapes": shapes,
        "ao": 0,
        "bm": 0,
    }


def doc(name: str, op: int, layers: list[J], size: int = 120) -> J:
    return {
        "v": "5.7.4",
        "nm": name,
        "fr": 30,
        "ip": 0,
        "op": op,
        "w": size,
        "h": size,
        "ddd": 0,
        "assets": [],
        "layers": layers,
    }


def studio_orb() -> J:
    """'Studio is live': a play button with two rings pulsing outward (loops, 2 s)."""
    op = 60
    rings = [
        layer(
            i + 2,
            f"ring{i}",
            transform(
                [60, 60],
                s=anim((delay, [60, 60, 100]), (delay + 40, [150, 150, 100])),
                o=anim((delay, [70]), (delay + 40, [0])),
            ),
            [group(ellipse(64), stroke(VIOLET if i == 0 else CORAL, 3))],
            op,
        )
        for i, delay in enumerate((0, 20))
    ]
    core = layer(
        1,
        "core",
        transform([60, 60], s=anim((0, [100, 100, 100]), (30, [108, 108, 100]), (60, [100, 100, 100]))),
        [
            group(path([[-8, -12], [-8, 12], [12, 0]], closed=True), fill(WHITE)),
            group(ellipse(56), fill(VIOLET)),
        ],
        op,
    )
    return doc("studio-orb", op, [core, *rings])


def empty_box() -> J:
    """Empty state: a card floating up and down with two twinkling sparkles (loops, 3 s)."""
    op = 90
    card = layer(
        1,
        "card",
        transform([60, 64], s=static([100, 100, 100]), r=anim((0, [-4]), (45, [4]), (90, [-4]))),
        [
            group(rect(30, 4, 2), fill(WHITE, 85)),
            group(rect(56, 42, 10), fill(VIOLET)),
        ],
        op,
    )
    card["ks"]["p"] = anim((0, [60, 66, 0]), (45, [60, 56, 0]), (90, [60, 66, 0]))
    sparkles = [
        layer(
            i + 2,
            f"sparkle{i}",
            transform(pos, s=anim((d, [0, 0, 100]), (d + 15, [100, 100, 100]), (d + 30, [0, 0, 100]))),
            [group(path([[0, -8], [0, 8]]), path([[-8, 0], [8, 0]]), stroke(CORAL, 3))],
            op,
        )
        for i, (pos, d) in enumerate((([92, 30], 0), ([26, 40], 40)))
    ]
    return doc("empty-box", op, [card, *sparkles])


def success_check() -> J:
    """Success: a circle pops in and a check mark draws itself (plays once, 1 s)."""
    op = 30
    trim = {"ty": "tm", "s": static(0), "e": anim((8, [0]), (24, [100])), "o": static(0), "m": 1}
    check = layer(
        1,
        "check",
        transform([60, 60]),
        [group(path([[-16, 1], [-5, 12], [17, -12]]), stroke(WHITE, 7), trim)],
        op,
    )
    circle = layer(
        2,
        "circle",
        transform([60, 60], s=anim((0, [0, 0, 100]), (10, [110, 110, 100]), (16, [100, 100, 100]))),
        [group(ellipse(80), fill(VIOLET))],
        op,
    )
    return doc("success-check", op, [check, circle])


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, build in (
        ("studio-orb", studio_orb),
        ("empty-box", empty_box),
        ("success-check", success_check),
    ):
        (OUT / f"{name}.json").write_text(json.dumps(build(), separators=(",", ":")) + "\n", encoding="utf-8")
        print("wrote", name)


if __name__ == "__main__":
    main()

"""Model answers that pass every check, for the discovery and blueprint tests."""

from __future__ import annotations

from typing import Any

WORDS = [
    "rent",
    "groceries",
    "laptop",
    "textbook",
    "scholarship",
    "tuition",
    "bus",
    "bicycle",
    "coffee",
    "pantry",
    "freezer",
    "lentils",
    "pasta",
    "spreadsheet",
    "envelope",
    "cashback",
    "receipt",
    "bank",
    "overdraft",
    "interest",
    "loan",
    "grant",
    "semester",
    "summer",
    "internship",
    "tutoring",
    "freelance",
    "resume",
    "interview",
    "stipend",
    "dorm",
    "roommate",
    "utilities",
    "internet",
    "phone",
    "subscription",
    "streaming",
    "gym",
    "library",
    "museum",
    "festival",
    "concert",
    "gift",
    "birthday",
    "holiday",
    "travel",
    "train",
    "flight",
    "hostel",
    "passport",
    "visa",
    "insurance",
    "pharmacy",
    "dentist",
    "optician",
    "laundry",
    "haircut",
    "thrift",
    "market",
]
PILLARS = ["Budgeting basics", "Food on a budget", "Student money admin", "Smart spending"]


def ideas(n: int = 52) -> list[dict[str, Any]]:
    out = []
    for i in range(n):
        n = len(WORDS)
        a, b, c = WORDS[i % n], WORDS[(i * 7 + 3) % n], WORDS[(i * 13 + 11) % n]
        out.append(
            {
                "title": f"{a.title()} {b} and {c} without stress",
                "format": "LONG" if i % 3 == 0 else "SHORT",
                "pillar": PILLARS[i % 4],
                "angle": f"Owner's own numbers for {a} and {b}.",
            }
        )
    return out


def calendar(idea_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
    longs = [i for i, x in enumerate(idea_list) if x["format"] == "LONG"]
    shorts = [i for i, x in enumerate(idea_list) if x["format"] == "SHORT"]
    entries = []
    for n, day in enumerate((2, 5, 9, 12, 16, 19, 23, 26)):
        entries.append({"day": day, "idea_ref": longs[n], "format": "LONG"})
    for n, day in enumerate((1, 3, 4, 6, 8, 10, 11, 13, 15, 17, 18, 20, 22, 24, 25, 27)):
        entries.append({"day": day, "idea_ref": shorts[n], "format": "SHORT"})
    return entries


def strategy() -> dict[str, Any]:
    idea_list = ideas()
    return {
        "positioning": "A student who shows their real monthly budget, mistakes included, explained plainly.",
        "target_audience": {
            "description": "University students on a tight budget",
            "needs": ["Simple budgets"],
        },
        "pillars": [{"name": p, "description": f"{p} for students"} for p in PILLARS],
        "formats": [
            {
                "name": "Budget walk-through",
                "format": "LONG",
                "description": "Screen recording",
                "owner_role": "voice",
            },
            {
                "name": "Price check",
                "format": "SHORT",
                "description": "One item, one tip",
                "owner_role": "voice",
            },
            {"name": "Q&A", "format": "LONG", "description": "Viewer questions", "owner_role": "on-camera"},
        ],
        "calendar_30d": calendar(idea_list),
        "ideas": idea_list,
        "growth_strategy": ["Answer common questions in Shorts and link the long explainer."],
        "risks": [
            {
                "risk": "Templated narrated slideshows may be judged inauthentic",
                "severity": "HIGH",
                "mitigation": "Owner narration and own examples in every video; rotate formats.",
            }
        ],
    }


def branding() -> dict[str, Any]:
    return {
        "name_ideas": [{"name": f"Budget Lab {n}", "reason": "Clear topic"} for n in range(1, 11)],
        "description": "Real student budgets, explained simply. No hype, just numbers you can check.",
        "tone": ["calm", "practical"],
        "palette": [
            {"hex": "#0F766E", "role": "primary"},
            {"hex": "#FDE68A", "role": "accent"},
            {"hex": "#111827", "role": "dark"},
            {"hex": "#F9FAFB", "role": "light"},
        ],
        "fonts": [{"family": "Inter", "use": "BODY"}, {"family": "Bebas Neue", "use": "HEADLINE"}],
        "logo_brief": "A simple piggy-bank outline made of a spreadsheet grid.",
        "banner_brief": "Teal background with a hand-drawn budget sheet.",
    }

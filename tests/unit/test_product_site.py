"""The public product site (site/product, ADR-0028) makes no promises and loads nothing from elsewhere."""

from __future__ import annotations

import re
from pathlib import Path

from tubeforge.research.forbidden import scan

SITE = Path(__file__).resolve().parents[2] / "site" / "product"


def _text(html: str) -> str:
    return re.sub(r"<[^>]+>", " ", html)


def test_product_pages_exist_and_make_no_promises() -> None:
    pages = sorted(SITE.glob("*.html"))
    assert [p.name for p in pages] == ["index.html", "privacy.html"]
    for page in pages:
        html = page.read_text(encoding="utf-8")
        assert scan(_text(html)) == [], page.name
        assert "not a prediction" in html.lower() or page.name != "index.html" or "never predicts" in html


def test_product_site_has_no_trackers_or_outside_scripts() -> None:
    for page in SITE.glob("*.html"):
        html = page.read_text(encoding="utf-8").lower()
        assert "<script" not in html and "<iframe" not in html, page.name
        assert not re.search(r"""(?:src|href)=["']https?://(?!github\.com/)""", html), page.name
        assert '<link rel="stylesheet" href="style.css"' in html

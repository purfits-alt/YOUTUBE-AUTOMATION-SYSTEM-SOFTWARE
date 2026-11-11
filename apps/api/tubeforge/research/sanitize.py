"""Fetched content → plain text (OAUTH_SECURITY §7 step 1).

HTML: scripts, styles, frames, embedded objects, SVG/MathML, forms and comments are dropped; only
visible text is kept, with line breaks at block elements. Feeds: RSS 2.0, RSS 1.0 (RDF) and Atom
are parsed with the standard library after refusing any document type declaration, so entity
expansion and external entities cannot happen. The result is length-capped and stripped of
control and invisible formatting characters that could hide instructions.
"""

from __future__ import annotations

import re
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from html.parser import HTMLParser

MAX_TEXT_CHARS = 200_000
MAX_FEED_ITEMS = 100
MAX_ITEM_CHARS = 4_000

_SKIP = {
    "script", "style", "noscript", "template", "iframe", "object", "embed", "svg", "math",
    "form", "button", "select", "textarea", "head", "canvas", "audio", "video", "picture",
}  # fmt: skip
_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
_BLOCK = {
    "p", "div", "br", "li", "ul", "ol", "tr", "table", "section", "article", "header", "footer",
    "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "pre", "hr", "dd", "dt", "figcaption",
}  # fmt: skip
_SPACES = re.compile(r"[ \t\f\v ]+")
_BLANKS = re.compile(r"\n\s*\n+")


def clean_text(text: str, limit: int = MAX_TEXT_CHARS) -> str:
    out = []
    for ch in text:
        if ch in "\n\t":
            out.append(ch)
            continue
        cat = unicodedata.category(ch)
        # Cc control, Cf format (zero-width, bidi overrides), Co private use, Cs surrogates.
        if cat in ("Cc", "Cf", "Co", "Cs"):
            continue
        out.append(ch)
    joined = _SPACES.sub(" ", "".join(out))
    lines = [line.strip() for line in joined.split("\n")]
    return _BLANKS.sub("\n\n", "\n".join(lines)).strip()[:limit]


class _TextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title: list[str] = []
        self._skip_depth = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "title":
            self._in_title = True
        if tag in _SKIP and tag not in _VOID:
            self._skip_depth += 1
        elif tag in _BLOCK and not self._skip_depth:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        if tag in _SKIP and tag not in _VOID and self._skip_depth:
            self._skip_depth -= 1
        elif tag in _BLOCK and not self._skip_depth:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title.append(data)
        elif not self._skip_depth:
            self.parts.append(data)


def html_to_text(markup: str, limit: int = MAX_TEXT_CHARS) -> tuple[str | None, str]:
    """Returns (title, visible text)."""
    parser = _TextParser()
    parser.feed(markup)
    parser.close()
    title = clean_text("".join(parser.title), 500) or None
    return title, clean_text("".join(parser.parts), limit)


class FeedError(ValueError):
    """The body is not a feed we can read safely."""


@dataclass(frozen=True)
class FeedItem:
    title: str
    link: str | None
    published: str | None
    summary: str


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _child_text(el: ET.Element, *names: str) -> str | None:
    for child in el:
        if _local(child.tag) in names:
            return "".join(child.itertext()).strip() or None
    return None


def _atom_link(el: ET.Element) -> str | None:
    fallback = None
    for child in el:
        if _local(child.tag) == "link" and child.get("href"):
            rel = child.get("rel", "alternate")
            if rel == "alternate":
                return child.get("href")
            fallback = fallback or child.get("href")
    return fallback


def parse_feed(body: bytes) -> tuple[str | None, list[FeedItem]]:
    """RSS 2.0 / RSS 1.0 / Atom → (feed title, items). Refuses DTDs and entity declarations."""
    head = body[:4096].lower()
    if b"<!doctype" in head or b"<!entity" in body.lower():
        raise FeedError("Feeds with a document type declaration are refused (entity expansion).")
    try:
        root = ET.fromstring(body)  # noqa: S314 - DTD/entities refused above
    except ET.ParseError as exc:
        raise FeedError(f"Not a readable feed: {exc}") from exc
    kind = _local(root.tag)
    if kind == "rss":
        channel = next((c for c in root if _local(c.tag) == "channel"), None)
        if channel is None:
            raise FeedError("RSS feed without a channel.")
        title = _child_text(channel, "title")
        entries = [c for c in channel if _local(c.tag) == "item"]
    elif kind == "rdf":
        channel = next((c for c in root if _local(c.tag) == "channel"), None)
        title = _child_text(channel, "title") if channel is not None else None
        entries = [c for c in root if _local(c.tag) == "item"]
    elif kind == "feed":
        title = _child_text(root, "title")
        entries = [c for c in root if _local(c.tag) == "entry"]
    else:
        raise FeedError("Not an RSS or Atom feed.")
    items: list[FeedItem] = []
    for entry in entries[:MAX_FEED_ITEMS]:
        raw_summary = _child_text(entry, "description", "summary", "content", "encoded") or ""
        _t, summary = html_to_text(raw_summary, MAX_ITEM_CHARS)
        link = _atom_link(entry) if kind == "feed" else _child_text(entry, "link")
        items.append(
            FeedItem(
                title=clean_text(_child_text(entry, "title") or "(untitled)", 500),
                link=link,
                published=_child_text(entry, "pubdate", "published", "updated", "date"),
                summary=summary,
            )
        )
    return (clean_text(title, 500) if title else None), items

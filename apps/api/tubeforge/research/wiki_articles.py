"""Wikipedia article text for research briefs (A09, Phase 7; source ``WIKIPEDIA_ARTICLES``).

Search (MediaWiki REST ``search/page``) and plain-text extracts (Action API ``prop=extracts``,
``explaintext``) on the channel-language Wikipedia. Each article is stored as a source document,
so every claim in a brief can cite it. Article text is CC BY-SA 4.0: briefs quote short passages
(≤ 300 characters) and keep the article URL for attribution.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlencode

from sqlalchemy.orm import Session

from tubeforge.research.fetcher import JSON_TYPES, FetchError, ResearchFetcher
from tubeforge.research.sources import get_source, require_usable, store_document

CODE = "WIKIPEDIA_ARTICLES"
LANGUAGES = ("en", "es", "fr", "de", "ur")
MAX_CHARS = 20_000


@dataclass(frozen=True)
class Article:
    title: str
    url: str
    document_id: str
    chars: int


def _lang(language: str) -> str:
    lang = language.strip().lower()
    if lang not in LANGUAGES:
        raise ValueError(f"No Wikipedia articles source for language '{language}'.")
    return lang


def _json(text: str) -> dict[str, Any]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise FetchError("Wikipedia returned something that is not JSON.") from exc
    if not isinstance(data, dict):
        raise FetchError("Wikipedia returned an unexpected answer.")
    return data


class WikipediaArticles:
    def __init__(self, db: Session, fetcher: ResearchFetcher) -> None:
        self._db = db
        self._fetcher = fetcher
        self._source = get_source(db, CODE)

    def _get(self, url: str) -> dict[str, Any]:
        require_usable(self._db, self._source)
        return _json(self._fetcher.get(url, self._source.allowed_hosts, accept=JSON_TYPES).text())

    def search(self, language: str, query: str, limit: int = 5) -> list[str]:
        lang = _lang(language)
        q = " ".join(query.split())[:200]
        if not q:
            return []
        url = f"https://{lang}.wikipedia.org/w/rest.php/v1/search/page?" + urlencode({"q": q, "limit": limit})
        pages = self._get(url).get("pages", [])
        return [str(p["title"]) for p in pages if isinstance(p, dict) and p.get("title")][:limit]

    def article(self, language: str, title: str) -> Article | None:
        lang = _lang(language)
        params = {
            "action": "query",
            "prop": "extracts",
            "explaintext": "1",
            "exsectionformat": "plain",
            "redirects": "1",
            "format": "json",
            "formatversion": "2",
            "titles": title[:255],
        }
        data = self._get(f"https://{lang}.wikipedia.org/w/api.php?" + urlencode(params))
        pages = (data.get("query") or {}).get("pages") or []
        page = pages[0] if pages and isinstance(pages[0], dict) else {}
        text = str(page.get("extract") or "").strip()
        if page.get("missing") or not text:
            return None
        real = str(page.get("title") or title)
        url = f"https://{lang}.wikipedia.org/wiki/{quote(real.replace(' ', '_'), safe='')}"
        doc = store_document(
            self._db,
            self._source,
            url=url,
            title=f"{real} — Wikipedia ({lang})",
            text=text[:MAX_CHARS],
            language=lang,
        )
        return Article(real, url, str(doc.id), min(len(text), MAX_CHARS))

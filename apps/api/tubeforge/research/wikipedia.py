"""Wikimedia pageviews (CHANNEL_DISCOVERY_SPEC §1 ``WIKIPEDIA_PAGEVIEWS``).

Daily pageviews per article, and the most-viewed articles of a day, from the Wikimedia Analytics
REST API (``wikimedia.org/api/rest_v1/metrics/pageviews``; pageview data is published as CC0).
Only human traffic (``agent=user``) across all access methods is used. Each response is stored
as a source document, so scores can cite it as evidence.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any
from urllib.parse import quote

from sqlalchemy.orm import Session

from tubeforge.research.fetcher import JSON_TYPES, FetchError, ResearchFetcher
from tubeforge.research.sources import get_source, require_usable, store_document

CODE = "WIKIPEDIA_PAGEVIEWS"
API = "https://wikimedia.org/api/rest_v1/metrics/pageviews"
PROJECT = re.compile(
    r"^[a-z]{2,12}(-[a-z]{2,12})*\."
    r"(wikipedia|wiktionary|wikibooks|wikinews|wikiquote|wikisource|wikiversity|wikivoyage)$"
)
MAX_DAYS = 400
NON_ARTICLES = re.compile(r"^(Main_Page|-|Special:.*|Wikipedia:.*|Portal:.*|Help:.*|File:.*|Talk:.*)$")


@dataclass(frozen=True)
class PageviewSeries:
    project: str
    article: str
    points: list[tuple[date, int]]
    document_id: str


@dataclass(frozen=True)
class TopArticles:
    project: str
    day: date
    articles: list[tuple[str, int, int]]  # (article, views, rank)
    document_id: str


def _check_project(project: str) -> str:
    project = project.strip().lower()
    if not PROJECT.match(project):
        raise ValueError("Use a Wikimedia project such as 'en.wikipedia'.")
    return project


def _article_key(article: str) -> str:
    key = article.strip().replace(" ", "_")
    if not key or len(key) > 255 or any(c in key for c in "#<>[]{}|\n\r\t"):
        raise ValueError("Not a valid article title.")
    return key


def _json(text: str) -> dict[str, Any]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise FetchError("Wikimedia returned something that is not JSON.") from exc
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        raise FetchError("Wikimedia returned an unexpected answer.")
    return data


class WikipediaPageviews:
    def __init__(self, db: Session, fetcher: ResearchFetcher) -> None:
        self._db = db
        self._fetcher = fetcher
        self._source = get_source(db, CODE)

    def _get(self, url: str) -> str:
        require_usable(self._db, self._source)
        return self._fetcher.get(url, self._source.allowed_hosts, accept=JSON_TYPES).text()

    def per_article(self, project: str, article: str, start: date, end: date) -> PageviewSeries:
        project, key = _check_project(project), _article_key(article)
        if start > end or (end - start).days > MAX_DAYS:
            raise ValueError(f"Choose a date range of at most {MAX_DAYS} days.")
        url = (
            f"{API}/per-article/{project}/all-access/user/{quote(key, safe='')}/daily/"
            f"{start:%Y%m%d}00/{end:%Y%m%d}00"
        )
        data = _json(self._get(url))
        points: list[tuple[date, int]] = []
        for item in data["items"]:
            stamp, views = str(item.get("timestamp", "")), item.get("views")
            if len(stamp) >= 8 and stamp[:8].isdigit() and isinstance(views, int) and views >= 0:
                points.append((datetime.strptime(stamp[:8], "%Y%m%d").date(), views))
        points.sort()
        lines = "\n".join(f"{d.isoformat()}: {v}" for d, v in points)
        doc = store_document(
            self._db,
            self._source,
            url=url,
            title=f"Pageviews · {key.replace('_', ' ')} · {project}",
            text=f"Daily Wikipedia pageviews (people, all access) for '{key}' on {project}:\n{lines}",
            language=project.split(".", 1)[0],
        )
        return PageviewSeries(project, key, points, str(doc.id))

    def top(self, project: str, day: date) -> TopArticles:
        project = _check_project(project)
        if day > date.today() - timedelta(days=1):
            raise ValueError("Top lists exist only for days that are over.")
        url = f"{API}/top/{project}/all-access/{day:%Y}/{day:%m}/{day:%d}"
        data = _json(self._get(url))
        rows: list[tuple[str, int, int]] = []
        for block in data["items"]:
            for a in block.get("articles", []) if isinstance(block, dict) else []:
                name, views, rank = a.get("article"), a.get("views"), a.get("rank")
                if (
                    isinstance(name, str)
                    and isinstance(views, int)
                    and isinstance(rank, int)
                    and not NON_ARTICLES.match(name)
                ):
                    rows.append((name, views, rank))
        rows.sort(key=lambda r: r[2])
        lines = "\n".join(f"{r}. {n.replace('_', ' ')}: {v}" for n, v, r in rows[:200])
        doc = store_document(
            self._db,
            self._source,
            url=url,
            title=f"Most-viewed articles · {project} · {day.isoformat()}",
            text=f"Most-viewed Wikipedia articles on {project} on {day.isoformat()} (people):\n{lines}",
            language=project.split(".", 1)[0],
        )
        return TopArticles(project, day, rows, str(doc.id))

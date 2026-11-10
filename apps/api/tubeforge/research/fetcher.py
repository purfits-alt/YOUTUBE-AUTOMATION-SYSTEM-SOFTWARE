"""The only HTTP client for research sources (OAUTH_SECURITY §6 limits).

2 MB maximum body, 15 s for the whole fetch, at most 3 redirects (each re-checked against the
allowlist and the address rules), and only HTML, XML/feeds or JSON responses. System proxy
settings are ignored so the address check sees the real server.
"""

from __future__ import annotations

import time
from collections.abc import Iterable
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version

import httpx

from tubeforge.config import get_settings
from tubeforge.research.net import (
    FetchBlockedError,
    Resolver,
    check_peer,
    check_resolution,
    check_url,
    system_resolver,
)

MAX_BYTES = 2 * 1024 * 1024
TIMEOUT_S = 15.0
MAX_REDIRECTS = 3
REDIRECTS = {301, 302, 303, 307, 308}
HTML_TYPES = ("text/html", "application/xhtml+xml")
FEED_TYPES = (
    "application/rss+xml",
    "application/atom+xml",
    "application/rdf+xml",
    "application/xml",
    "text/xml",
)
JSON_TYPES = ("application/json",)
ALL_TYPES = HTML_TYPES + FEED_TYPES + JSON_TYPES
_now = time.monotonic  # replaced in tests


class FetchError(Exception):
    """The server could not give us the page (HTTP error, timeout, too big, wrong type). May be retried."""


@dataclass(frozen=True)
class Fetched:
    url: str
    content_type: str
    body: bytes
    charset: str

    def text(self) -> str:
        try:
            return self.body.decode(self.charset, errors="replace")
        except LookupError:
            return self.body.decode("utf-8", errors="replace")


def _version() -> str:
    try:
        return version("tubeforge")
    except PackageNotFoundError:  # pragma: no cover - always installed via uv sync
        return "0"


def user_agent(contact: str | None = None) -> str:
    contact = get_settings().research_contact if contact is None else contact
    return f"TubeForge/{_version()} (self-hosted research tool{'; ' + contact if contact else ''})"


def _media_type(header: str) -> tuple[str, str]:
    parts = [p.strip() for p in header.split(";")]
    charset = "utf-8"
    for p in parts[1:]:
        if p.lower().startswith("charset="):
            charset = p.split("=", 1)[1].strip("\"' ") or "utf-8"
    return parts[0].lower(), charset


class ResearchFetcher:
    def __init__(
        self,
        *,
        transport: httpx.BaseTransport | None = None,
        resolver: Resolver = system_resolver,
        contact: str | None = None,
    ) -> None:
        self._resolver = resolver
        self._http = httpx.Client(
            transport=transport,
            timeout=httpx.Timeout(TIMEOUT_S),
            follow_redirects=False,
            trust_env=False,
            headers={"User-Agent": user_agent(contact), "Accept-Encoding": "gzip, deflate"},
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> ResearchFetcher:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def get(self, url: str, allowed_hosts: Iterable[str], *, accept: tuple[str, ...] = ALL_TYPES) -> Fetched:
        hosts = list(allowed_hosts)
        deadline = _now() + TIMEOUT_S
        for _hop in range(MAX_REDIRECTS + 1):
            checked = check_url(url, hosts)
            check_resolution(checked.host, self._resolver)
            try:
                with self._http.stream("GET", checked.url, headers={"Accept": ", ".join(accept)}) as resp:
                    check_peer(resp)
                    if resp.status_code in REDIRECTS:
                        location = resp.headers.get("location")
                        if not location:
                            raise FetchError(f"Redirect without a target (HTTP {resp.status_code}).")
                        url = str(httpx.URL(checked.url).join(location))
                        continue
                    if resp.status_code != 200:
                        raise FetchError(f"The site answered HTTP {resp.status_code}.")
                    media, charset = _media_type(resp.headers.get("content-type", ""))
                    if media not in accept:
                        raise FetchError(f"Unexpected content type '{media or 'none'}'.")
                    declared = resp.headers.get("content-length")
                    if declared and declared.isdigit() and int(declared) > MAX_BYTES:
                        raise FetchError("The page is larger than 2 MB.")
                    chunks: list[bytes] = []
                    size = 0
                    for chunk in resp.iter_bytes():
                        size += len(chunk)
                        if size > MAX_BYTES:
                            raise FetchError("The page is larger than 2 MB.")
                        if _now() > deadline:
                            raise FetchError("The site took longer than 15 seconds.")
                        chunks.append(chunk)
                    body = b"".join(chunks)
                    return Fetched(url=checked.url, content_type=media, body=body, charset=charset)
            except httpx.TimeoutException as exc:
                raise FetchError("The site took longer than 15 seconds.") from exc
            except httpx.HTTPError as exc:
                raise FetchError(f"Could not reach the site ({type(exc).__name__}).") from exc
        raise FetchBlockedError("Too many redirects (more than 3).")

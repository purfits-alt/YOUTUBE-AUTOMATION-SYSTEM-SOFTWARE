"""URL and address checks for research fetches (OAUTH_SECURITY §6 "Research fetcher" row).

A URL may be fetched only if all of these hold:

- the scheme is ``https``, with no user info and no port other than 443;
- the host is a DNS name (never an IP literal) that the source's allowlist names exactly;
- the host is not a YouTube or Google page (anti-scraping, ADR-0015);
- **every** address the name resolves to is a public unicast address. Private, loopback,
  link-local, CGNAT, multicast, reserved and documentation ranges are refused, and so are
  IPv4-mapped or NAT64 forms of them.

After the connection opens, :func:`check_peer` re-checks the address actually connected to, so a
DNS answer that changes between the check and the connection (DNS rebinding) is still caught
before any response body is read.
"""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable, Iterable
from dataclasses import dataclass

import httpx

# Hosts no research source may name (anti-scraping: YouTube pages and Google search/Trends HTML).
BLOCKED_SUFFIXES = (
    "youtube.com",
    "youtu.be",
    "youtube-nocookie.com",
    "googlevideo.com",
    "ytimg.com",
    "google.com",
)
_NAT64 = ipaddress.ip_network("64:ff9b::/96")
_CGNAT = ipaddress.ip_network("100.64.0.0/10")

Resolver = Callable[[str, int], Iterable[str]]


class FetchBlockedError(Exception):
    """The request would break the outbound policy. Never retried."""


@dataclass(frozen=True)
class CheckedUrl:
    url: str
    host: str


def system_resolver(host: str, port: int) -> list[str]:
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return [str(info[4][0]) for info in infos]


def is_blocked_host(host: str) -> bool:
    host = host.lower().rstrip(".")
    return any(host == s or host.endswith("." + s) for s in BLOCKED_SUFFIXES)


def is_public_ip(value: str) -> bool:
    try:
        ip = ipaddress.ip_address(value.split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None:
            return is_public_ip(str(ip.ipv4_mapped))
        if ip in _NAT64:
            return is_public_ip(str(ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)))
        if ip.sixtofour is not None or ip.teredo is not None:
            return False
    if isinstance(ip, ipaddress.IPv4Address) and ip in _CGNAT:
        return False
    return ip.is_global and not ip.is_multicast and not ip.is_reserved


def _is_ip_literal(host: str) -> bool:
    try:
        ipaddress.ip_address(host.strip("[]"))
        return True
    except ValueError:
        pass
    # Shorthand forms the URL parser may accept and resolvers turn into addresses
    # ("2130706433", "0x7f.1", "127.1"): refuse anything made only of digits, dots and hex marks.
    return all(part.isdigit() or part.lower().startswith("0x") for part in host.split(".") if part)


def check_url(url: str, allowed_hosts: Iterable[str]) -> CheckedUrl:
    """Static checks (no network). Raises FetchBlockedError with a plain-language reason."""
    try:
        parsed = httpx.URL(url)
    except (httpx.InvalidURL, TypeError, ValueError) as exc:
        raise FetchBlockedError(f"Not a valid web address: {exc}") from exc
    if parsed.scheme != "https":
        raise FetchBlockedError("Only https:// addresses can be fetched.")
    if parsed.userinfo:
        raise FetchBlockedError("Addresses with a user name or password are not allowed.")
    if parsed.port not in (None, 443):
        raise FetchBlockedError("Only the standard https port (443) is allowed.")
    try:
        host = parsed.raw_host.decode("ascii").lower().rstrip(".")
    except UnicodeDecodeError as exc:  # pragma: no cover - httpx IDNA-encodes hosts
        raise FetchBlockedError("The host name is not valid.") from exc
    if not host or _is_ip_literal(host):
        raise FetchBlockedError("Use a host name, not an IP address.")
    if is_blocked_host(host):
        raise FetchBlockedError("YouTube and Google pages are never fetched (no scraping, ADR-0015).")
    allowed = {h.lower().rstrip(".") for h in allowed_hosts}
    if host not in allowed:
        raise FetchBlockedError(f"{host} is not on this source's allowlist.")
    return CheckedUrl(url=str(parsed), host=host)


def check_resolution(host: str, resolver: Resolver) -> None:
    try:
        addresses = list(resolver(host, 443))
    except OSError as exc:
        raise FetchBlockedError(f"{host} could not be found ({exc}).") from exc
    if not addresses:
        raise FetchBlockedError(f"{host} could not be found.")
    bad = [a for a in addresses if not is_public_ip(a)]
    if bad:
        raise FetchBlockedError(f"{host} points to a private or local address; it is blocked.")


def check_peer(response: httpx.Response) -> None:
    """Re-check the address actually connected to (no-op when the transport does not expose it)."""
    stream = response.extensions.get("network_stream")
    if stream is None:
        return
    addr = stream.get_extra_info("server_addr")
    if addr and not is_public_ip(str(addr[0])):
        raise FetchBlockedError("The connection went to a private or local address; it was stopped.")

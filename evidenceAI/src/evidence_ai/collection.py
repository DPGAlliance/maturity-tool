import ipaddress
import socket
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urlsplit
from urllib.parse import urljoin

import httpx


MAX_DIRECT_URLS = 10
MAX_RESPONSE_BYTES = 1_000_000
MAX_EXCERPT_CHARS = 4_000


@dataclass(frozen=True)
class CollectedPage:
    url: str
    title: str
    excerpt: str
    source_type: str
    provider: str | None = None
    fetched_at: datetime | None = None
    links: list[str] | None = None


class _ReadableHtml(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.text: list[str] = []
        self.links: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self._ignored_depth += 1
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                url = urljoin(self.base_url, href)
                if urlsplit(url).scheme in {"http", "https"} and url not in self.links:
                    self.links.append(url)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self._ignored_depth:
            self._ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth:
            self.text.append(data)


def _is_public_url(url: str) -> tuple[bool, str | None]:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False, "URL must use http or https with a hostname"
    if parsed.username or parsed.password or (parsed.port not in {None, 80, 443}):
        return False, "URL credentials and non-standard ports are not allowed"
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(parsed.hostname, None)}
        if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
            return False, "URL must resolve only to public IP addresses"
    except socket.gaierror:
        return False, "URL hostname could not be resolved"
    return True, None


def supplied_urls(context: dict[str, object]) -> list[str]:
    candidates = [context.get("website_url"), context.get("repository_url")]
    candidates.extend(context.get("documentation_urls", []))
    candidates.extend(item.get("url") for item in context.get("provided_resources", []) if isinstance(item, dict))
    urls: list[str] = []
    for value in candidates:
        if isinstance(value, str) and value not in urls:
            urls.append(value)
    return urls[:MAX_DIRECT_URLS]


def fetch_supplied_page(url: str, client: httpx.Client) -> tuple[CollectedPage | None, str | None]:
    allowed, reason = _is_public_url(url)
    if not allowed:
        return None, f"Skipped {url}: {reason}."
    try:
        with client.stream("GET", url, follow_redirects=False) as response:
            if response.is_redirect:
                return None, f"Skipped {url}: redirects are not followed."
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").lower()
            if not (content_type.startswith("text/") or "json" in content_type):
                return None, f"Skipped {url}: unsupported content type."
            body = b""
            for chunk in response.iter_bytes():
                body += chunk
                if len(body) > MAX_RESPONSE_BYTES:
                    return None, f"Skipped {url}: response exceeded 1 MB."
    except httpx.HTTPError as error:
        return None, f"Could not fetch {url}: {error}."

    decoded = body.decode(response.encoding or "utf-8", errors="replace")
    links: list[str] = []
    if content_type.startswith("text/html"):
        parser = _ReadableHtml(url)
        parser.feed(decoded)
        text = " ".join(" ".join(parser.text).split())
        links = parser.links[:50]
    else:
        text = " ".join(decoded.split())
    return CollectedPage(
        url=url,
        title=urlsplit(url).hostname or url,
        excerpt=text[:MAX_EXCERPT_CHARS],
        source_type="supplied",
        fetched_at=datetime.now(timezone.utc),
        links=links,
    ), None

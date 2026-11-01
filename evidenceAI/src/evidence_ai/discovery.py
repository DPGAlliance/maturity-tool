import os
from dataclasses import dataclass
from pathlib import Path

import httpx


@dataclass(frozen=True)
class DiscoveryResult:
    url: str
    title: str
    excerpt: str
    provider: str


def _brave_api_key() -> str | None:
    value = os.getenv("EVIDENCE_AI_BRAVE_SEARCH_API_KEY")
    if value:
        return value.strip()

    secret_file = os.getenv("EVIDENCE_AI_BRAVE_SEARCH_API_KEY_FILE")
    if secret_file:
        return Path(secret_file).read_text().strip()
    return None


def discover_with_brave(
    query: str, client: httpx.Client, limit: int = 5
) -> tuple[list[DiscoveryResult], list[str]]:
    """Return bounded public web-search candidates without fetching their URLs."""
    api_key = _brave_api_key()
    if not api_key:
        return [], ["Brave Search is not configured; discovery was skipped."]

    try:
        response = client.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": query, "count": min(limit, 20)},
            headers={"Accept": "application/json", "X-Subscription-Token": api_key},
        )
        response.raise_for_status()
    except httpx.HTTPError as error:
        return [], [f"Brave Search failed: {error}"]

    results: list[DiscoveryResult] = []
    for item in response.json().get("web", {}).get("results", [])[:limit]:
        url = item.get("url")
        if not isinstance(url, str) or not url:
            continue
        results.append(
            DiscoveryResult(
                url=url,
                title=str(item.get("title", "")),
                excerpt=str(item.get("description", "")),
                provider="brave",
            )
        )
    return results, []


def discover_product_sources(
    product_name: str, organization_name: str | None, client: httpx.Client
) -> tuple[list[DiscoveryResult], list[str]]:
    organization = f" {organization_name}" if organization_name else ""
    return discover_with_brave(f"{product_name}{organization} official documentation source code", client)

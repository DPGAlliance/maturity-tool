import socket

import httpx

from evidence_ai.collection import fetch_supplied_page, supplied_urls


def test_supplied_urls_deduplicates_and_caps_urls() -> None:
    urls = [f"https://docs.example.org/{index}" for index in range(12)]
    context = {
        "website_url": urls[0],
        "repository_url": urls[0],
        "documentation_urls": urls[1:],
    }

    assert supplied_urls(context) == urls[:10]


def test_fetch_supplied_page_rejects_private_addresses() -> None:
    page, warning = fetch_supplied_page("http://127.0.0.1/internal", httpx.Client())

    assert page is None
    assert "public IP addresses" in warning


def test_fetch_supplied_page_limits_and_normalizes_text(monkeypatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))],
    )

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "text/html"}, content=b"<script>ignore()</script><p>hello\n world</p><a href='/policy'>Policy</a>")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        page, warning = fetch_supplied_page("https://example.org/docs", client)

    assert warning is None
    assert page and page.excerpt == "hello world Policy"
    assert page.links == ["https://example.org/policy"]

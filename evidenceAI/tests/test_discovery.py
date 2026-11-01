import httpx

from evidence_ai.discovery import DiscoveryResult, discover_with_brave


def test_brave_discovery_returns_bounded_candidates(monkeypatch) -> None:
    monkeypatch.setenv("EVIDENCE_AI_BRAVE_SEARCH_API_KEY", "test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Subscription-Token"] == "test-key"
        return httpx.Response(
            200,
            json={
                "web": {
                    "results": [
                        {"url": "https://docs.example.org", "title": "Docs", "description": "Guide"},
                        {"url": "https://code.example.org", "title": "Code", "description": "Repository"},
                    ]
                }
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        results, warnings = discover_with_brave("DIGIT Core", client, limit=1)

    assert warnings == []
    assert results == [
        DiscoveryResult(url="https://docs.example.org", title="Docs", excerpt="Guide", provider="brave")
    ]


def test_brave_discovery_skips_when_unconfigured(monkeypatch) -> None:
    monkeypatch.delenv("EVIDENCE_AI_BRAVE_SEARCH_API_KEY", raising=False)
    monkeypatch.delenv("EVIDENCE_AI_BRAVE_SEARCH_API_KEY_FILE", raising=False)

    with httpx.Client() as client:
        results, warnings = discover_with_brave("DIGIT Core", client)

    assert results == []
    assert warnings == ["Brave Search is not configured; discovery was skipped."]

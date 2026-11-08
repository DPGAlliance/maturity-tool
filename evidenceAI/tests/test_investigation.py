import json
import socket

import httpx

from evidence_ai.investigation import _github_files, investigate


def test_investigation_executes_only_model_selected_allow_listed_actions(monkeypatch) -> None:
    monkeypatch.setenv("EVIDENCE_AI_OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("EVIDENCE_AI_BRAVE_SEARCH_API_KEY", "test-key")
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))],
    )
    actions = iter(
        [
            {"action": "read_existing_link", "url": "https://docs.example.org"},
            {"action": "list_github_repository", "repository": "example/product"},
            {"action": "read_github_file", "repository": "example/product", "path": "ARCHITECTURE.md"},
            {"action": "brave_search", "gap": "governance"},
            {"action": "finish"},
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.openai.com":
            return httpx.Response(200, json={"output": [{"content": [{"type": "output_text", "text": json.dumps(next(actions))}]}]})
        if request.url.host == "docs.example.org":
            return httpx.Response(200, headers={"content-type": "text/html"}, text="<p>Documentation</p>")
        if request.url.host == "api.github.com" and request.url.path.endswith("/git/trees/HEAD"):
            return httpx.Response(200, json={"tree": [{"path": "ARCHITECTURE.md", "type": "blob"}]})
        if request.url.host == "api.github.com":
            return httpx.Response(200, text="Modular extension architecture")
        if request.url.host == "api.search.brave.com":
            return httpx.Response(200, json={"web": {"results": [{"url": "https://example.org/governance", "title": "Governance", "description": "Steering group"}]}})
        raise AssertionError(f"Unexpected request: {request.url}")

    context = {"documentation_urls": ["https://docs.example.org"], "repository_url": "https://github.com/example/product"}
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        pages, trace, warnings = investigate(context, "Example Product", client)

    assert warnings == []
    assert [entry["outcome"] for entry in trace] == ["collected", "listed", "collected", "discovered", "finished"]
    assert [page.source_type for page in pages] == ["supplied", "github", "discovered"]
    assert pages[1].url == "https://github.com/example/product/blob/HEAD/ARCHITECTURE.md"


def test_investigation_rejects_links_not_in_shared_context(monkeypatch) -> None:
    monkeypatch.setenv("EVIDENCE_AI_OPENAI_API_KEY", "test-key")
    actions = iter([
        {"action": "read_existing_link", "url": "https://untrusted.example.org"},
        {"action": "finish"},
    ])

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.openai.com"
        return httpx.Response(200, json={"output": [{"content": [{"type": "output_text", "text": json.dumps(next(actions))}]}]})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        pages, trace, warnings = investigate({}, "Example Product", client)

    assert pages == []
    assert warnings == []
    assert trace[0]["outcome"] == "rejected"
    assert "allow-listed" in trace[0]["reason"]


def test_github_listing_prioritizes_evidence_artifacts() -> None:
    files = [{"path": f"services/service-{index}.py", "type": "blob"} for index in range(50)]
    files.extend([
        {"path": "LICENSE", "type": "blob"},
        {"path": "docs/architecture.md", "type": "blob"},
    ])

    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"tree": files}))) as client:
        listed, warning = _github_files("example/product", client)

    assert warning is None
    assert listed[:2] == ["docs/architecture.md", "LICENSE"]

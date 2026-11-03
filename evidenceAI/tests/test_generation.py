import httpx

from evidence_ai.collection import CollectedPage
from evidence_ai.generation import DraftSuggestion, generate_draft_suggestions


def test_generation_keeps_only_cited_draft_suggestions(monkeypatch) -> None:
    monkeypatch.setenv("EVIDENCE_AI_OPENAI_API_KEY", "test-key")
    page = CollectedPage("https://docs.example.org", "Docs", "Evidence", "supplied")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer test-key"
        assert "evidence_summary" in request.content.decode()
        return httpx.Response(
            200,
            json={
                "output": [
                    {
                        "content": [
                            {
                                "type": "output_text",
                                "text": '{"suggestions":[{"indicator_id":"license","answer":"Apache-2.0","rationale":"The docs state this.","confidence":"high","citations":["https://docs.example.org"]}]}',
                            }
                        ]
                    }
                ]
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = generate_draft_suggestions([page], ["all"], client)

    assert result.warnings == []
    assert result.outcome == "generated"
    assert result.suggestions == [
        DraftSuggestion("license", "Apache-2.0", "The docs state this.", "high", [page.url])
    ]


def test_generation_skips_when_unconfigured(monkeypatch) -> None:
    monkeypatch.delenv("EVIDENCE_AI_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("EVIDENCE_AI_OPENAI_API_KEY_FILE", raising=False)

    with httpx.Client() as client:
        result = generate_draft_suggestions([], ["all"], client)

    assert result.suggestions == []
    assert result.outcome == "not_configured"
    assert result.warnings == ["OpenAI is not configured; no draft suggestions were generated."]

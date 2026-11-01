from fastapi import FastAPI


app = FastAPI(
    title="EvidenceAI",
    version="0.1.0",
    description="Evidence collection and validation service scaffold.",
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

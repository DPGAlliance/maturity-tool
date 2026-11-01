from fastapi import FastAPI

from evidence_ai.routes.autofill_jobs import router as autofill_jobs_router


app = FastAPI(
    title="EvidenceAI",
    version="0.1.0",
    description="MAT evidence collection and suggestion service.",
)

app.include_router(autofill_jobs_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

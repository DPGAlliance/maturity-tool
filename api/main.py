from dotenv import load_dotenv
from fastapi import FastAPI

from api.routes.metrics import router as metrics_router
from api.routes.repos import router as repos_router
from api.routes.summaries import router as summaries_router
from storage.db import init_db


def create_app() -> FastAPI:
    load_dotenv()
    init_db()

    app = FastAPI(title="Maturity Tool API", version="0.1.0")
    app.include_router(repos_router)
    app.include_router(metrics_router)
    app.include_router(summaries_router)
    return app


app = create_app()

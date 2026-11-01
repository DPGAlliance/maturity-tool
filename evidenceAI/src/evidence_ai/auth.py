import os
from pathlib import Path

from fastapi import HTTPException, Request, status


def get_secret(name: str) -> str | None:
    value = os.getenv(name)
    if value:
        return value.strip()

    value_file = os.getenv(f"{name}_FILE")
    if value_file:
        try:
            return Path(value_file).read_text(encoding="utf-8").strip()
        except OSError:
            return None
    return None


def require_api_key(request: Request) -> None:
    api_key = get_secret("EVIDENCE_AI_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="EvidenceAI API key is not configured",
        )

    authorization = request.headers.get("Authorization", "")
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
        )
    if authorization.removeprefix("Bearer ").strip() != api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )

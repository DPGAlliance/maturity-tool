import os

from dotenv import load_dotenv
from fastapi import Depends, HTTPException, Request, status

from storage.db import get_session


def get_db_session():
    session = get_session()
    try:
        yield session
    finally:
        session.close()


def require_api_key(request: Request):
    load_dotenv()
    api_key = os.getenv("API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="API_KEY is not configured",
        )

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
        )
    token = auth_header.replace("Bearer ", "", 1).strip()
    if token != api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )

    return True

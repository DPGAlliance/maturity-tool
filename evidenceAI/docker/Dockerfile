FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md /app/
COPY alembic.ini /app/
COPY alembic /app/alembic
COPY src /app/src

RUN pip install --no-cache-dir .

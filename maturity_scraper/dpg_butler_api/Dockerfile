FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

# System deps (minimal)
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY dpg_butler_api/requirements.txt /app/dpg_butler_api/requirements.txt

RUN pip install --no-cache-dir -r /app/dpg_butler_api/requirements.txt

# Copy full repo because we run from source
COPY . /app

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

# System deps (minimal)
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY data_viewer/requirements.txt /app/data_viewer/requirements.txt

COPY maturity_tools /app/maturity_tools

WORKDIR /app/data_viewer
RUN pip install --no-cache-dir -r requirements.txt
WORKDIR /app

# Copy full repo because we run from source
COPY . /app

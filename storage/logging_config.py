from __future__ import annotations

import logging
import os


DEFAULT_LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
DEFAULT_LOG_DATEFMT = os.getenv("LOG_DATEFMT", "%Y-%m-%dT%H:%M:%S")
DEFAULT_LOG_FORMAT = os.getenv(
    "LOG_FORMAT",
    "%(asctime)s.%(msecs)03d %(levelname)s %(name)s [%(filename)s:%(lineno)d] %(message)s",
)


def configure_logging(level: str | int | None = None) -> None:
    logging.basicConfig(
        level=level or DEFAULT_LOG_LEVEL,
        format=DEFAULT_LOG_FORMAT,
        datefmt=DEFAULT_LOG_DATEFMT,
        force=True,
    )

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler


DEFAULT_LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
DEFAULT_LOG_DATEFMT = os.getenv("LOG_DATEFMT", "%Y-%m-%dT%H:%M:%S")
DEFAULT_LOG_FORMAT = os.getenv(
    "LOG_FORMAT",
    "%(asctime)s.%(msecs)03d %(levelname)s %(name)s [%(filename)s:%(lineno)d] %(message)s",
)
STATUS_LOG_PATH = os.getenv("STATUS_LOG_PATH", "logs/refresh_status.log")
STATUS_LOG_MAX_BYTES = int(os.getenv("STATUS_LOG_MAX_BYTES", "5242880"))
STATUS_LOG_BACKUP_COUNT = int(os.getenv("STATUS_LOG_BACKUP_COUNT", "5"))
STATUS_LOG_FORMAT = os.getenv(
    "STATUS_LOG_FORMAT",
    "%(asctime)s | %(name)s | %(message)s",
)


def configure_logging(level: str | int | None = None) -> None:
    logging.basicConfig(
        level=level or DEFAULT_LOG_LEVEL,
        format=DEFAULT_LOG_FORMAT,
        datefmt=DEFAULT_LOG_DATEFMT,
        force=True,
    )

    status_logger = logging.getLogger("refresh.status")
    if status_logger.handlers:
        return

    status_logger.setLevel(logging.INFO)
    status_logger.propagate = False
    formatter = logging.Formatter(STATUS_LOG_FORMAT, datefmt=DEFAULT_LOG_DATEFMT)

    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.INFO)
    stream_handler.setFormatter(formatter)

    log_dir = os.path.dirname(STATUS_LOG_PATH)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
    file_handler = RotatingFileHandler(
        STATUS_LOG_PATH,
        maxBytes=STATUS_LOG_MAX_BYTES,
        backupCount=STATUS_LOG_BACKUP_COUNT,
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)

    status_logger.addHandler(stream_handler)
    status_logger.addHandler(file_handler)

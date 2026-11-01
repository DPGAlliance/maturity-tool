from __future__ import annotations

import os
from pathlib import Path
from typing import Final


_MAX_SECRET_BYTES: Final[int] = 1024 * 1024  # 1 MiB safety cap


def get_secret(name: str, *, default: str | None = None, required: bool = False) -> str | None:
    """Return a secret from environment, supporting Docker secrets.

    Resolution order:
    1) If `${NAME}_FILE` is set, read the file contents.
    2) Else use `${NAME}`.

    Whitespace is stripped. If `required=True` and the secret is missing/empty,
    raises `RuntimeError`.
    """

    file_env = os.getenv(f"{name}_FILE")
    if file_env:
        path = Path(file_env)
        try:
            data = path.read_bytes()
        except FileNotFoundError as exc:
            raise RuntimeError(f"Secret file not found for {name}: {path}") from exc
        if len(data) > _MAX_SECRET_BYTES:
            raise RuntimeError(f"Secret file too large for {name}: {path}")
        value = data.decode("utf-8", errors="strict").strip()
    else:
        value = os.getenv(name)
        value = value.strip() if value is not None else None

    if (value is None or value == "") and default is not None:
        value = default

    if required and (value is None or value == ""):
        raise RuntimeError(
            f"Missing required secret: {name}. Set {name} or {name}_FILE."
        )

    return value

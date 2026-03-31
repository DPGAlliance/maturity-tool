#!/usr/bin/env bash
set -euo pipefail

if ! command -v poetry >/dev/null 2>&1; then
  echo "Poetry is required. Install it from https://python-poetry.org/docs/#installation" >&2
  exit 1
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

poetry -C "$repo_root/dpg_butler_api" export -f requirements.txt -o "$repo_root/dpg_butler_api/requirements.txt" --without-hashes
poetry -C "$repo_root/data_viewer" export -f requirements.txt -o "$repo_root/data_viewer/requirements.txt" --without-hashes
poetry -C "$repo_root/scripts" export -f requirements.txt -o "$repo_root/scripts/requirements.txt" --without-hashes

python - "$repo_root/data_viewer/requirements.txt" "$repo_root/scripts/requirements.txt" <<'PY'
import re
import sys
from pathlib import Path

PATTERNS = {
    "maturity-tools": "../maturity_tools",
    "maturity-storage": "../storage",
}

for file_path in sys.argv[1:]:
    path = Path(file_path)
    text = path.read_text(encoding="utf-8")
    for name, replacement in PATTERNS.items():
        text = re.sub(
            rf"({re.escape(name)}\s+@\s+)file://[^\s]+/(maturity_tools|storage)",
            rf"\1{replacement}",
            text,
        )
    path.write_text(text, encoding="utf-8")
PY

echo "Requirements refreshed."

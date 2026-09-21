#!/usr/bin/env bash
# HKUST e-Tendering Automation - run the app

cd "$(dirname "$0")" || exit 1

if ! command -v uv >/dev/null 2>&1; then
  echo "[ERROR] 'uv' is not installed. Run setup.sh first to check prerequisites." >&2
  echo "         Install uv from https://docs.astral.sh/uv/getting-started/installation/" >&2
  exit 1
fi

exec uv run python app.py "$@"

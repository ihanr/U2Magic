#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
export PYTHONUTF8=1
export U2_WEBUI_HOST="${U2_WEBUI_HOST:-0.0.0.0}"
export U2_WEBUI_PORT="${U2_WEBUI_PORT:-18765}"

if [ ! -x ".venv/bin/python" ]; then
  echo "Python venv not found. Run: python3 -m venv .venv"
  exit 1
fi

exec ./.venv/bin/python webui.py

#!/bin/sh
set -eu

mkdir -p /runtime/logs

if [ ! -f /runtime/webui_config.json ]; then
    cp /opt/u2-scripts-defaults/webui_config.json /runtime/webui_config.json
fi

exec /app/.venv/bin/python /app/webui.py


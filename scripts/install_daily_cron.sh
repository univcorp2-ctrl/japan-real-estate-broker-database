#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Python executable not found: $PYTHON_BIN" >&2
  echo "Create the virtual environment first: python -m venv .venv && .venv/bin/pip install -r requirements.txt -e ." >&2
  exit 1
fi

CRON_LINE="0 9 * * * cd '$ROOT_DIR' && '$PYTHON_BIN' scripts/run_daily.py >> '$ROOT_DIR/logs/cron.log' 2>&1"
CURRENT_CRON="$(crontab -l 2>/dev/null || true)"
FILTERED_CRON="$(printf '%s\n' "$CURRENT_CRON" | grep -v "scripts/run_daily.py" || true)"
{
  printf '%s\n' "$FILTERED_CRON"
  printf '%s\n' "$CRON_LINE"
} | awk 'NF' | crontab -

echo "Installed daily cron job at 09:00 local time."
echo "$CRON_LINE"

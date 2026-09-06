#!/bin/sh
set -eu

DASHBOARD_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_ROOT=$(dirname "$DASHBOARD_DIR")
ASSISTANT_DB_PATH=${ASSISTANT_DB_PATH:-"$PROJECT_ROOT/assistant.db"}
export ASSISTANT_DB_PATH

if [ ! -x "$PROJECT_ROOT/.venv/bin/personal-assistant-dashboard-api" ]; then
  echo "The project environment is not ready. Run: python3 -m venv .venv && .venv/bin/python -m pip install -e ."
  exit 1
fi

if ! command -v node >/dev/null 2>&1 || ! command -v pnpm >/dev/null 2>&1; then
  echo "Node.js 22 and pnpm are required to run the dashboard. Install them, then try again."
  exit 1
fi
PNPM_COMMAND=$(command -v pnpm)

API_PROCESS=""
if curl -fsS http://127.0.0.1:8765/api/dashboard >/dev/null 2>&1; then
  echo "Using the existing local data service."
else
  "$PROJECT_ROOT/.venv/bin/personal-assistant-dashboard-api" &
  API_PROCESS=$!
fi

cleanup() {
  if [ -n "$API_PROCESS" ]; then
    kill "$API_PROCESS" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

if curl -fsS http://localhost:3000/ >/dev/null 2>&1; then
  echo "The dashboard is already running at http://localhost:3000"
  exit 0
fi

cd "$DASHBOARD_DIR"
CI=true "$PNPM_COMMAND" dev

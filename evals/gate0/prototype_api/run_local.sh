#!/usr/bin/env bash
# Run the whole Kinetiq v3 live prototype LOCALLY with a real webcam -- API + PWA, one command.
# The bash twin of run_local.ps1 (which is the primary, since this project's dev machine is Windows).
#
# Starts, and leaves running until Ctrl+C:
#   1. prototype_api (this repo)            -> http://localhost:$API_PORT
#   2. kinetiq-demo3 (the sibling PWA repo) -> http://localhost:$PWA_PORT
#
# WHY NO HTTPS IS NEEDED HERE: http://localhost is a SECURE CONTEXT by browser spec, so the camera
# works, and an HTTP page calling an HTTP API is same-scheme so there's no mixed content either.
# That only holds for localhost -- to reach this from a PHONE, both sides must be HTTPS. See
# "kinetiq v3/DEPLOY_RUNBOOK.md".
#
# Needs internet on first run: the PWA fetches the MediaPipe pose model from a CDN.
#
# Usage:
#   ./run_local.sh                    # API 8000, PWA 8080
#   API_PORT=8001 PWA_PORT=8081 ./run_local.sh
#   DEMO3_PATH=/path/to/kinetiq-demo3 ./run_local.sh
set -euo pipefail

API_PORT="${API_PORT:-8000}"
PWA_PORT="${PWA_PORT:-8080}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"   # .../evals/gate0/prototype_api
GATE0_DIR="$(dirname "$SCRIPT_DIR")"                          # .../evals/gate0
REPO_ROOT="$(dirname "$(dirname "$GATE0_DIR")")"              # .../kinetiq-v2
WORKSPACE="$(dirname "$REPO_ROOT")"                           # .../product-workspace
DEMO3_PATH="${DEMO3_PATH:-$WORKSPACE/kinetiq-demo3}"

if [ ! -f "$DEMO3_PATH/index.html" ]; then
  echo "ERROR: kinetiq-demo3 not found at: $DEMO3_PATH (no index.html there)." >&2
  echo "       It is a SEPARATE git repo that normally sits next to kinetiq-v2." >&2
  echo "       Set DEMO3_PATH=/path/to/kinetiq-demo3 and re-run." >&2
  exit 1
fi

PY="${PYTHON:-python}"
command -v "$PY" >/dev/null 2>&1 || PY=python3
command -v "$PY" >/dev/null 2>&1 || { echo "ERROR: no python on PATH." >&2; exit 1; }

# localhost and 127.0.0.1 are DIFFERENT origins to the browser -- allow both so it works either way.
export PROTOTYPE_API_CORS_ORIGINS="http://localhost:${PWA_PORT},http://127.0.0.1:${PWA_PORT}"

echo
echo "Kinetiq v3 live prototype -- LOCAL run"
echo "  API  : $GATE0_DIR"
echo "  PWA  : $DEMO3_PATH"
echo "  CORS : $PROTOTYPE_API_CORS_ORIGINS"
echo

API_PID=""; PWA_PID=""
cleanup() {
  echo; echo "Shutting down..."
  [ -n "$API_PID" ] && kill "$API_PID" 2>/dev/null || true
  [ -n "$PWA_PID" ] && kill "$PWA_PID" 2>/dev/null || true
  echo "Stopped."
}
trap cleanup EXIT INT TERM

# Same invocation shape as the container CMD (CWD=evals/gate0 so gate_config/detector/golden_loader resolve).
echo "Starting prototype_api on http://localhost:${API_PORT} ..."
( cd "$GATE0_DIR" && exec "$PY" -m uvicorn prototype_api.main:app --host 127.0.0.1 --port "$API_PORT" ) &
API_PID=$!

echo "Starting kinetiq-demo3 on http://localhost:${PWA_PORT} ..."
( cd "$DEMO3_PATH" && exec "$PY" -m http.server "$PWA_PORT" --bind 127.0.0.1 ) &
PWA_PID=$!

for _ in $(seq 1 30); do
  sleep 0.5
  if curl -sf "http://127.0.0.1:${API_PORT}/health" >/dev/null 2>&1; then
    OK=1; break
  fi
  kill -0 "$API_PID" 2>/dev/null || { echo "ERROR: prototype_api exited early." >&2; exit 1; }
done
[ "${OK:-0}" = "1" ] || { echo "ERROR: prototype_api did not answer /health within ~15s." >&2; exit 1; }

echo
echo "  /health OK"
echo
echo "=================================================================="
echo "  OPEN THIS IN YOUR BROWSER:  http://localhost:${PWA_PORT}"
echo "=================================================================="
echo
echo "  First time only -- on the home screen, paste this into 'API URL' and Save:"
echo "      http://localhost:${API_PORT}"
echo "  (localStorage; overrides config.js without disturbing the deployed Render URL in it.)"
echo
echo "  Then: allow camera -> pick Squat -> Start -> ~5 reps -> Stop -> Validate"
echo "        -> enter your real rep count -> Summary -> Export bundle (.zip)"
echo
echo "  Full click-by-click + how to score the export: README.md section"
echo "  'Running the whole prototype locally (real webcam)'."
echo
echo "  Press Ctrl+C to stop both servers."
echo

wait

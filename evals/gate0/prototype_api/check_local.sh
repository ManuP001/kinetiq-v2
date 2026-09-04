#!/usr/bin/env bash
# One-command "does it all talk" check -- run this before handing a deployed URL to anyone.
# Catches "the server isn't running" / "wrong port" / "CORS origin typo" class of problems in
# seconds, without needing a phone or a browser. See README.md's "Deploying for a real gym
# session" section.
#
# Usage:
#   ./check_local.sh                              # checks http://127.0.0.1:8000 (a local dev run)
#   ./check_local.sh https://your-tunnel-url.com   # checks a deployed/tunneled instance
set -euo pipefail

BASE_URL="${1:-http://127.0.0.1:8000}"
BASE_URL="${BASE_URL%/}"

echo "Checking ${BASE_URL} ..."

echo -n "1. GET /health ... "
HEALTH_BODY=$(curl -sf "${BASE_URL}/health") || { echo "FAILED (no response -- is prototype_api running/reachable?)"; exit 1; }
python -c "
import json, sys
d = json.loads('''$HEALTH_BODY''')
assert d.get('status') == 'ok', f'unexpected /health body: {d!r}'
assert 'squat' in d.get('supported_exercises', []), f'squat missing from supported_exercises: {d!r}'
" || { echo "FAILED (unexpected /health body: $HEALTH_BODY)"; exit 1; }
echo "ok"

echo -n "2. POST /prototype/assess (one synthetic frame) ... "
ASSESS_BODY=$(curl -sf -X POST "${BASE_URL}/prototype/assess" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "check-local",
    "exercise_id": "squat",
    "reset": true,
    "frames": [{
      "t_ms": 0, "pose_model": "blazepose_33",
      "people": [{"track_id": 0, "kp": [[0.5, 0.5, 0.0, 0.9]], "box": [0.4, 0.4, 0.2, 0.2]}]
    }]
  }') || { echo "FAILED (no response / non-2xx -- check CORS/PROTOTYPE_API_CORS_ORIGINS if this is a deployed URL and you're calling from a browser instead; curl itself isn't subject to CORS)"; exit 1; }
python -c "
import json, sys
d = json.loads('''$ASSESS_BODY''')
assert 'rep_count' in d, f'unexpected /prototype/assess body: {d!r}'
assert d['rep_count'] == 0, f'expected rep_count 0 for a single static frame, got {d!r}'
" || { echo "FAILED (unexpected body: $ASSESS_BODY)"; exit 1; }
echo "ok"

echo
echo "All checks passed. ${BASE_URL} is reachable and talking correctly."
echo "(This only checks the API. Run the phone smoke test in DEPLOY_RUNBOOK.md before the real session --"
echo " it's the only thing that proves the PWA's own CORS/mixed-content/model-loading path works too.)"

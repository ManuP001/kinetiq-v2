#!/usr/bin/env bash
# Path A (recommended for the first gym session): a cloudflared QUICK TUNNEL exposes a locally-
# running prototype_api over a temporary HTTPS URL. Preferred over ngrok: ngrok's free tier shows
# an interstitial warning page on first load that blocks the PWA's fetch() calls outright (a
# browser fetch can't click through it); cloudflared's quick tunnel has no such page and needs no
# signup or account. See README.md's "Deploying for a real gym session" section.
#
# Trade-off (DEPLOY_RUNBOOK.md): the laptop running this must stay on and online for the whole
# session, and the URL is NOT stable -- it changes every time this script (re)starts.
#
# Prereq: prototype_api must already be running locally in another terminal:
#   cd evals/gate0 && python -m prototype_api
#
# Usage: ./tunnel.sh [port]   (default 8000, matching prototype_api/__main__.py's default)
set -euo pipefail

PORT="${1:-8000}"

if ! command -v cloudflared >/dev/null 2>&1; then
  echo "error: cloudflared is not installed." >&2
  echo "Install it, then re-run this script:" >&2
  echo "  macOS:   brew install cloudflared" >&2
  echo "  Windows: winget install --id Cloudflare.cloudflared" >&2
  echo "  Linux/other: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/" >&2
  exit 1
fi

if ! curl -sf "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then
  echo "error: nothing answered http://127.0.0.1:${PORT}/health -- start prototype_api first, in another terminal:" >&2
  echo "  cd evals/gate0 && python -m prototype_api" >&2
  echo "(or ./check_local.sh to confirm)" >&2
  exit 1
fi

echo "prototype_api is up on port ${PORT}. Starting the cloudflared quick tunnel..."
echo
echo "Watch the output below for a line containing an HTTPS URL like:"
echo "  https://<random-words>.trycloudflare.com"
echo
echo "That URL is what you set as kinetiq-demo3's API base URL (index.html's home screen, or"
echo "config.js's default -- see README.md). It changes every time this script restarts, so"
echo "re-check it if you stop/restart the tunnel mid-setup."
echo
echo "Ctrl+C stops the tunnel -- the phone loses API access immediately when you do."
echo

exec cloudflared tunnel --url "http://127.0.0.1:${PORT}"

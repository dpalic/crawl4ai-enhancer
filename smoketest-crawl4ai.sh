#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

# Verify a virtual environment exists before running tests.
if [ ! -d ".venv" ]; then
  echo "Missing .venv; run ./run.sh first to create the environment." >&2
  exit 1
fi

# shellcheck disable=SC1091
source .venv/bin/activate

# Choose which target to test: enhancer or upstream Crawl4AI.
# Defaults aim for local runs; you can override via environment or the prompts.
TARGET_DEFAULT="upstream"
TARGET="${TARGET:-$TARGET_DEFAULT}"
ENHANCER_BASE_URL="${ENHANCER_BASE_URL:-http://localhost:8000}"
UPSTREAM_BASE_URL="${UPSTREAM_BASE_URL:-http://localhost:11235}"

# Prompt for which service URL to test.
echo "Which service do you want to test?"
echo "  enhancer = the crawl4ai-enhancer proxy"
echo "  upstream = the original Crawl4AI service"
echo "Default: $TARGET_DEFAULT (timeout 5s)"
read -r -t 5 -p "Target [ enhancer / upstream ]: " USER_TARGET || true
if [ -n "${USER_TARGET:-}" ]; then
  TARGET="$USER_TARGET"
fi

# Suggest a base URL based on the chosen target.
if [ "$TARGET" = "enhancer" ]; then
  SUGGESTED_URL="$ENHANCER_BASE_URL"
else
  SUGGESTED_URL="$UPSTREAM_BASE_URL"
fi

echo "Enter base URL to test. Default: $SUGGESTED_URL"
read -r -t 5 -p "Base URL [ $SUGGESTED_URL ]: " USER_URL || true

if [ -n "${USER_URL:-}" ]; then
  export CRAWL4AI_BASE_URL="$USER_URL"
  echo "Testing at $CRAWL4AI_BASE_URL (user selection)"
else
  export CRAWL4AI_BASE_URL="$SUGGESTED_URL"
  echo "Testing at $CRAWL4AI_BASE_URL (default for target $TARGET)"
fi

pytest -s tests/test_crawl4ai_api.py

echo "Smoke tests completed against $CRAWL4AI_BASE_URL"

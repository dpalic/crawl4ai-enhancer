#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"

# Perform an HTTP GET for the given path and report the outcome.
get() {
  local path="$1"
  local url="${BASE_URL%/}${path}"
  local tmp
  local status
  local exit_code=0

  tmp="$(mktemp)"

  echo "GET ${url}"
  status="$(curl -sS -o "$tmp" -w "%{http_code}" "$url" || true)"

  if [[ "$status" != "200" ]]; then
    # Fail when the endpoint does not return HTTP 200.
    echo "❌ ${path} returned status ${status}"
    echo "Body:"
    cat "$tmp"
    exit_code=1
  else
    # Report success and echo the response body for visibility.
    echo "✅ ${path} status ${status}"
    echo "Body:"
    cat "$tmp"
    echo
  fi

  rm -f "$tmp"
  return "$exit_code"
}

# Run the suite of smoke checks and summarize results.
main() {
  local failures=0
  local exit_code=0

  get "/api/health" || failures=$((failures + 1))

  if [[ $failures -ne 0 ]]; then
    # Surface the number of failed endpoints to upstream callers.
    echo "Smoke test failed with ${failures} error(s)."
    exit_code=1
  else
    # Confirm success when all endpoints pass.
    echo "Smoke test passed."
  fi

  return "$exit_code"
}

main "$@"
exit_code=$?
exit "$exit_code"

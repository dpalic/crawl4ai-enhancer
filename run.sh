#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

# Prepare a Python virtual environment if it does not already exist.
ensure_venv() {
  local exit_code=0
  if [ ! -d ".venv" ]; then
    # Create a dedicated virtual environment to isolate dependencies.
    python -m venv .venv || exit_code=$?
  fi
  return "$exit_code"
}

# Activate the virtual environment for dependency management and execution.
activate_venv() {
  local exit_code=0
  # shellcheck disable=SC1091
  source .venv/bin/activate || exit_code=$?
  return "$exit_code"
}

# Install or upgrade required dependencies for local development.
install_dependencies() {
  local exit_code=0
  python -m pip install --upgrade pip || exit_code=$?
  python -m pip install -r requirements-dev.txt || exit_code=$?
  return "$exit_code"
}

# Ensure an environment file is present to configure the application.
ensure_env_file() {
  local exit_code=0
  ENV_FILE=".env"
  if [ ! -f "$ENV_FILE" ]; then
    # Seed .env from the example to provide defaults when none are set.
    if [ -f ".env.example" ]; then
      cp .env.example "$ENV_FILE" || exit_code=$?
      if [ "$exit_code" -eq 0 ]; then
        echo "Created $ENV_FILE from .env.example"
      fi
    else
      # Fail fast when no configuration files exist so the service is not misconfigured.
      echo "Missing $ENV_FILE and .env.example; please provide one." >&2
      exit_code=1
    fi
  fi
  return "$exit_code"
}

# Load environment variables to allow downstream path adjustments.
load_environment() {
  local exit_code=0
  set -a
  source "$ENV_FILE" || exit_code=$?
  set +a
  return "$exit_code"
}

# Adjust data paths for local host runs to avoid permission issues on /data.
configure_paths_for_host() {
  local exit_code=0
  local in_container=0
  if [ -f "/.dockerenv" ]; then
    # Detect Docker so we keep the container mount points intact.
    in_container=1
  fi

  if [ "$in_container" -eq 0 ]; then
    # Override DATA_DIR to a writable project path when running on the host.
    if [ "${DATA_DIR:-/data}" = "/data" ]; then
      DATA_DIR="$ROOT_DIR/data"
    fi
    mkdir -p "$DATA_DIR" || exit_code=$?

    # Point SQLite URL to the host data directory when using the default.
    if [ "${DB_URL:-sqlite:////data/app.db}" = "sqlite:////data/app.db" ]; then
      DB_URL="sqlite:///$DATA_DIR/app.db"
    fi
    export DATA_DIR DB_URL
  fi

  return "$exit_code"
}

# Launch the FastAPI application with auto-reload for local development.
start_app() {
  local exit_code=0
  local log_level="${LOG_LEVEL:-info}"
  uvicorn app.main:app --reload --env-file "$ENV_FILE" --host 0.0.0.0 --port 8000 --log-level "$log_level" || exit_code=$?
  return "$exit_code"
}

# Orchestrate setup steps and start the application.
main() {
  local exit_code=0
  ensure_venv || exit_code=$?
  if [ "$exit_code" -eq 0 ]; then
    # Proceed only when the virtual environment is ready.
    activate_venv || exit_code=$?
  fi

  if [ "$exit_code" -eq 0 ]; then
    # Install dependencies after activation succeeds.
    install_dependencies || exit_code=$?
  fi

  if [ "$exit_code" -eq 0 ]; then
    # Ensure a configuration file exists before loading settings.
    ensure_env_file || exit_code=$?
  fi

  if [ "$exit_code" -eq 0 ]; then
    # Load settings so subsequent steps can adjust paths.
    load_environment || exit_code=$?
  fi

  if [ "$exit_code" -eq 0 ]; then
    # Adjust data and DB paths for host runs before launching the app.
    configure_paths_for_host || exit_code=$?
  fi

  if [ "$exit_code" -eq 0 ]; then
    # Start the FastAPI application once setup completes.
    start_app || exit_code=$?
  fi

  return "$exit_code"
}

main "$@"
exit_code=$?
exit "$exit_code"

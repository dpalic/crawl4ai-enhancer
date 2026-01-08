import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import httpx
from fastapi import FastAPI

from app.api.routes import health, proxy
from app.core.config import UpstreamEndpoint, get_settings
from app.core.logging_utils import attach_request_id_filter_to_root
from app.services.upstream_registry import UpstreamRegistry


def _configure_logging_from_env() -> None:
    """
    Set root logger level from LOG_LEVEL env (defaults to INFO) and attach a basic
    console handler when none exists so app logs are visible.
    """
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    if level_name == "TRACE":
        # Branch: custom TRACE level requested.
        from app.core.logging_utils import TRACE_LEVEL_NUM
        level = TRACE_LEVEL_NUM
    else:
        # Branch: standard log level name provided.
        level = getattr(logging, level_name, logging.INFO)
    root = logging.getLogger()
    if not root.handlers:
        # Branch: no handlers yet; attach console handler.
        logging.basicConfig(
            level=level,
            format="%(asctime)s %(levelname)s %(name)s [req=%(request_id)s]: %(message)s",
        )
    root.setLevel(level)


def _sanitize_db_url(url: str) -> str:
    """
    Redact credentials from a DB URL before logging so secrets do not appear in startup output.
    Returns the original URL when no username/password is present; otherwise replaces the
    password with *** while keeping host and database name for diagnostics.
    """
    redacted_url = "***"
    try:
        parsed = urlsplit(url)
        if not parsed.username and not parsed.password:
            # Branch: no credentials present; use original URL.
            redacted_url = url
        else:
            netloc_parts = []
            if parsed.username:
                # Branch: include username when present.
                netloc_parts.append(parsed.username)
            if parsed.password:
                # Branch: redact password.
                netloc_parts.append("***")
            userinfo = ":".join(netloc_parts) if netloc_parts else ""
            if userinfo:
                userinfo = f"{userinfo}@"
            host = parsed.hostname or ""
            port = f":{parsed.port}" if parsed.port else ""
            netloc = f"{userinfo}{host}{port}"
            redacted_url = urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))
    except Exception:
        # Branch: parsing failed; return placeholder.
        redacted_url = "***"
    return redacted_url


def _settings_snapshot(settings) -> dict:
    """
    Produce a startup snapshot of key settings, redacting secrets, so operators can confirm
    runtime configuration (paths, upstream URL, timeouts) without exposing credentials.

    Args:
        settings: Settings instance to summarize.

    Returns:
        Dict with redacted settings summary.
    """
    upstream_source = "file" if settings.upstreams_file else "env"
    snapshot = {
        "app_name": settings.app_name,
        "version": settings.version,
        "data_dir": settings.data_dir,
        "db_url": _sanitize_db_url(settings.db_url),
        "upstream_base_url": settings.upstream_base_url,
        "upstream_primary_name": settings.upstream_primary_name,
        "upstream_source": upstream_source,
        "upstream_timeout_seconds": settings.upstream_default_timeout_seconds,
        "upstream_auth_header_set": bool(settings.upstream_auth_header),
    }
    return snapshot


def _build_upstream_registry(settings) -> UpstreamRegistry:
    """
    Initialize the upstream registry for either single-URL or multi-upstream mode.
    """
    if settings.upstreams:
        # Branch: multi-upstream mode sourced from UPSTREAMS_FILE.
        endpoints = settings.upstreams
    else:
        # Branch: single-upstream mode; synthesize one endpoint from env settings.
        endpoints = [
            UpstreamEndpoint(
                name=settings.upstream_primary_name or "primary",
                url=settings.upstream_base_url,
                group="default",
                auth_header=settings.upstream_auth_header or "",
                weight=1,
                timeout_seconds=settings.upstream_default_timeout_seconds,
                is_default=True,
            )
        ]
    registry = UpstreamRegistry(
        upstreams=endpoints,
        default_auth_header=settings.upstream_auth_header,
        default_timeout_seconds=settings.upstream_default_timeout_seconds,
    )
    return registry


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    settings = get_settings()
    _configure_logging_from_env()
    logger = logging.getLogger(__name__)

    # Attach request-id filter to all handlers so %(request_id)s works across the app.
    attach_request_id_filter_to_root()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """FastAPI lifespan context to set up and tear down shared resources."""
        Path(settings.data_dir).mkdir(parents=True, exist_ok=True)
        # Shared async HTTP client for upstream calls (connection pooling, timeouts).
        app.state.http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(settings.upstream_default_timeout_seconds, connect=10.0),
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
            follow_redirects=True,
        )
        # Shared upstream registry to track health and selection (single or multi mode).
        app.state.upstream_registry = _build_upstream_registry(settings)
        root_level = logging.getLogger().getEffectiveLevel()
        logger_level = logger.getEffectiveLevel()
        upstream_mode = "multi" if settings.upstreams else "single"
        upstream_count = len(settings.upstreams) if settings.upstreams else 1
        primary_name = settings.upstream_primary_name or (
            settings.upstreams[0].name if settings.upstreams else "primary"
        )
        snapshot = _settings_snapshot(settings)
        logger.info(
            "Startup %s v%s | data_dir=%s | upstream=%s (%s mode, count=%s, primary=%s) | log_levels root=%s app=%s",
            settings.app_name,
            settings.version,
            settings.data_dir,
            settings.upstream_base_url,
            upstream_mode,
            upstream_count,
            primary_name,
            logging.getLevelName(root_level),
            logging.getLevelName(logger_level),
        )
        logger.debug(
            "Starting %s v%s | data_dir=%s | upstream=%s",
            settings.app_name,
            settings.version,
            settings.data_dir,
            settings.upstream_base_url,
        )
        logger.info("Startup config (redacted): %s", snapshot)
        yield
        await app.state.http_client.aclose()
        logger.debug("Shutdown complete for %s", settings.app_name)

    app = FastAPI(title=settings.app_name, version=settings.version, lifespan=lifespan)
    app.include_router(health.router, prefix="/api")
    app.include_router(proxy.router)
    return app


app = create_app()

from contextlib import asynccontextmanager
from pathlib import Path
import logging
import os
from urllib.parse import urlsplit, urlunsplit
from fastapi import FastAPI

from app.api.routes import health, proxy
from app.core.config import get_settings
from app.core.logging_utils import attach_request_id_filter_to_root


def _configure_logging_from_env() -> None:
    """
    Set root logger level from LOG_LEVEL env (defaults to INFO) and attach a basic
    console handler when none exists so app logs are visible.
    """
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    if level_name == "TRACE":
        from app.core.logging_utils import TRACE_LEVEL_NUM
        level = TRACE_LEVEL_NUM
    else:
        level = getattr(logging, level_name, logging.INFO)
    root = logging.getLogger()
    if not root.handlers:
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
    try:
        parsed = urlsplit(url)
        if not parsed.username and not parsed.password:
            return url
        netloc_parts = []
        if parsed.username:
            netloc_parts.append(parsed.username)
        if parsed.password:
            netloc_parts.append("***")
        userinfo = ":".join(netloc_parts) if netloc_parts else ""
        if userinfo:
            userinfo = f"{userinfo}@"
        host = parsed.hostname or ""
        port = f":{parsed.port}" if parsed.port else ""
        netloc = f"{userinfo}{host}{port}"
        return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))
    except Exception:
        return "***"


def _settings_snapshot(settings) -> dict:
    """
    Produce a startup snapshot of key settings, redacting secrets, so operators can confirm
    runtime configuration (paths, upstream URL, timeouts) without exposing credentials.
    """
    return {
        "app_name": settings.app_name,
        "version": settings.version,
        "data_dir": settings.data_dir,
        "db_url": _sanitize_db_url(settings.db_url),
        "upstream_base_url": settings.upstream_base_url,
        "upstream_timeout_seconds": settings.upstream_timeout_seconds,
        "upstream_auth_header_set": bool(settings.upstream_auth_header),
    }


def create_app() -> FastAPI:
    settings = get_settings()
    _configure_logging_from_env()
    logger = logging.getLogger(__name__)

    # Attach request-id filter to all handlers so %(request_id)s works across the app.
    attach_request_id_filter_to_root()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        Path(settings.data_dir).mkdir(parents=True, exist_ok=True)
        root_level = logging.getLogger().getEffectiveLevel()
        logger_level = logger.getEffectiveLevel()
        logger.info(
            "Startup %s v%s | data_dir=%s | upstream=%s | log_levels root=%s app=%s",
            settings.app_name,
            settings.version,
            settings.data_dir,
            settings.upstream_base_url,
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
        logger.info("Startup config (redacted): %s", _settings_snapshot(settings))
        yield
        logger.debug("Shutdown complete for %s", settings.app_name)

    app = FastAPI(title=settings.app_name, version=settings.version, lifespan=lifespan)
    app.include_router(health.router, prefix="/api")
    app.include_router(proxy.router)
    return app


app = create_app()

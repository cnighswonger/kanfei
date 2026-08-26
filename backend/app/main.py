"""FastAPI application factory and lifespan for Davis Weather Station.

The web application reads sensor data from SQLite and proxies hardware
commands to the logger daemon via IPC.  All serial/polling logic lives
in logger_main.py.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.responses import FileResponse, JSONResponse

from .config import settings
from .version import VERSION
from .models.database import init_database
from .ipc.client import IPCClient
from .ipc.dependencies import set_ipc_client
from .api.router import api_router
from .api import backgrounds as backgrounds_api
from .ws.handler import websocket_endpoint
from .services.log_buffer import install as install_log_buffer
from .services.public_mode import is_public_mode

# kanfei-nowcast is an optional add-on package.
try:
    from .services.nowcast_service import create_nowcast_service
    _NOWCAST_AVAILABLE = True
except ImportError:
    _NOWCAST_AVAILABLE = False

# Logging is configured in one shared place so that every entrypoint gets
# the same credential suppression — see app/logging_setup.py and #206, where
# the logger daemon lacked this and leaked WU credentials to the journal.
from .logging_setup import configure_logging, LOG_FMT, LOG_DATEFMT

_LOG_FMT = LOG_FMT
_LOG_DATEFMT = LOG_DATEFMT
configure_logging(level=logging.INFO)
logger = logging.getLogger(__name__)


def _unify_uvicorn_log_format() -> None:
    """Override uvicorn's formatters so access/error logs match our format."""
    fmt = logging.Formatter(_LOG_FMT, datefmt=_LOG_DATEFMT)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        for handler in logging.getLogger(name).handlers:
            handler.setFormatter(fmt)


# How often the nowcast supervisor checks for config changes (seconds).
_NOWCAST_SUPERVISOR_POLL = 30


async def _nowcast_supervisor(
    nc_config,
    nc_storage,
    nc_events,
) -> None:
    """Background supervisor that manages the nowcast service lifecycle.

    Polls ``nowcast_enabled`` and ``nowcast_mode`` from the DB every
    ``_NOWCAST_SUPERVISOR_POLL`` seconds and starts, stops, or restarts
    the nowcast service as needed — no app restart required.
    """
    from .services.nowcast import service_ref
    from .services.nowcast.remote_client import NowcastRemoteClient

    active_mode: str | None = None   # "remote", "local", or None (stopped)
    active_task: asyncio.Task | None = None

    def _stop_current() -> None:
        nonlocal active_task, active_mode
        if active_task is not None:
            active_task.cancel()
            logger.info("Nowcast service stopped (was %s)", active_mode)
            active_task = None
        service_ref.nowcast_service = None
        # Clear kanfei_nowcast.service reference if it was set
        try:
            import kanfei_nowcast.service as _svc_mod
            _svc_mod.nowcast_service = None
        except ImportError:
            pass
        active_mode = None

    def _start_remote() -> None:
        nonlocal active_task, active_mode
        nc_service = NowcastRemoteClient(nc_config, nc_storage, nc_events)
        service_ref.nowcast_service = nc_service
        active_task = asyncio.create_task(nc_service.start())
        active_mode = "remote"
        logger.info(
            "Nowcast service started: REMOTE (%s)",
            nc_config.get("nowcast_remote_url"),
        )

    def _start_local() -> None:
        nonlocal active_task, active_mode
        if not _NOWCAST_AVAILABLE:
            logger.warning(
                "Nowcast local mode requested but kanfei-nowcast package "
                "is not installed. Install kanfei-nowcast or switch to "
                "remote mode in Settings."
            )
            return
        nc_service = create_nowcast_service(nc_config, nc_storage, nc_events)
        service_ref.nowcast_service = nc_service
        # Also store in kanfei_nowcast.service for the full API module
        try:
            import kanfei_nowcast.service as _svc_mod
            _svc_mod.nowcast_service = nc_service
        except ImportError:
            pass
        active_task = asyncio.create_task(nc_service.start())
        active_mode = "local"
        logger.info("Nowcast service started: LOCAL")

    logger.info("Nowcast supervisor started (poll every %ds)", _NOWCAST_SUPERVISOR_POLL)

    while True:
        try:
            enabled = nc_config.get_bool("nowcast_enabled", False)
            mode = nc_config.get("nowcast_mode", "local")

            if not enabled:
                # Should be off — stop if running
                if active_mode is not None:
                    _stop_current()
                    logger.info("Nowcast disabled via config")
            elif mode != active_mode:
                # Mode changed (or first start) — restart with new mode
                if active_mode is not None:
                    _stop_current()
                if mode == "remote":
                    _start_remote()
                else:
                    _start_local()
            # else: enabled and same mode — nothing to do

            # If the service task died unexpectedly, restart it
            if active_task is not None and active_task.done():
                exc = active_task.exception() if not active_task.cancelled() else None
                if exc:
                    logger.error("Nowcast service crashed: %s — restarting", exc)
                else:
                    logger.warning("Nowcast service exited unexpectedly — restarting")
                old_mode = active_mode
                _stop_current()
                if enabled:
                    if old_mode == "remote":
                        _start_remote()
                    else:
                        _start_local()
        except Exception:
            logger.exception("Nowcast supervisor tick failed")

        await asyncio.sleep(_NOWCAST_SUPERVISOR_POLL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: database init and IPC client setup."""

    # Apply unified log format now that uvicorn's handlers are registered.
    _unify_uvicorn_log_format()

    # Capture WARNING+ to in-memory ring buffer for the System log viewer.
    install_log_buffer()

    # Initialize database (creates tables, enables WAL)
    logger.info("Database: %s", settings.db_path)
    init_database()
    logger.info("Database initialised")

    # Create IPC client for talking to the logger daemon
    client = IPCClient(settings.ipc_port)
    set_ipc_client(client)

    try:
        available = await client.is_available()
        if available:
            logger.info("Logger daemon connected via IPC (port %d)", settings.ipc_port)
        else:
            logger.warning(
                "Logger daemon not available on port %d — running in degraded mode",
                settings.ipc_port,
            )
    except Exception:
        logger.warning("Logger daemon not reachable — running in degraded mode")

    # Construct nowcast adapters — shared by all nowcast modes.
    from .models.database import SessionLocal
    from .ws.handler import ws_manager
    from .services.nowcast.kanfei_adapters import (
        KanfeiConfigProvider,
        KanfeiStorageBackend,
        KanfeiEventEmitter,
    )

    nc_config = KanfeiConfigProvider(SessionLocal)
    nc_storage = KanfeiStorageBackend(SessionLocal)
    nc_events = KanfeiEventEmitter(ws_manager)

    # Start nowcast supervisor — always runs, polls config each cycle.
    # Handles enable/disable and mode changes without requiring a restart.
    nowcast_supervisor_task = asyncio.create_task(
        _nowcast_supervisor(nc_config, nc_storage, nc_events)
    )

    # Start backup scheduler — always runs, polls config each cycle.
    # Handles enable/disable, schedule changes, and interval changes
    # without requiring a restart.
    from .services.backup import backup_scheduler, get_backup_dir
    backup_dir = get_backup_dir(
        settings.db_path,
        nc_config.get("backup_directory", ""),
    )
    backup_task = asyncio.create_task(
        backup_scheduler(settings.db_path, backup_dir)
    )

    # Start Telegram bot supervisor — always runs, polls config each cycle.
    # Handles enable/disable and token changes without requiring a restart.
    # Receives alert events via IPC and nowcast events via the event emitter.
    from .services.telegram import telegram_bot_supervisor
    telegram_task = asyncio.create_task(
        telegram_bot_supervisor(settings.db_path, settings.ipc_port, nc_events)
    )

    # Start Discord bot supervisor — same pattern as Telegram.
    from .services.discord_bot import discord_bot_supervisor
    discord_task = asyncio.create_task(
        discord_bot_supervisor(settings.db_path, settings.ipc_port, nc_events)
    )

    # Start APRS map collector if map is enabled (hot-reloads via config check).
    from .services.aprs_map_collector import start as start_aprs_map, stop_collector as stop_aprs_map
    aprs_map_started = False
    try:
        from .api.config import get_effective_config
        from .models.database import SessionLocal
        _db = SessionLocal()
        _cfg = get_effective_config(_db)
        _db.close()
        if _cfg.get("map_enabled"):
            lat = float(_cfg.get("latitude", 0))
            lon = float(_cfg.get("longitude", 0))
            callsign = str(_cfg.get("cwop_callsign", ""))
            if lat and lon:
                await start_aprs_map(lat, lon, radius_miles=200, own_callsign=callsign)
                aprs_map_started = True
    except Exception:
        logger.debug("APRS map collector startup skipped", exc_info=True)

    yield

    if aprs_map_started:
        await stop_aprs_map()
    if discord_task is not None:
        discord_task.cancel()
    if telegram_task is not None:
        telegram_task.cancel()
    if backup_task is not None:
        backup_task.cancel()
    if nowcast_supervisor_task is not None:
        nowcast_supervisor_task.cancel()
    await client.close()
    logger.info("Application shutdown complete")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Kanfei Weather Station",
        version=VERSION,
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    # CORS — configurable origin allowlist.
    # Default: empty (same-origin only, since SPA is served by the same uvicorn).
    # Set KANFEI_CORS_ORIGINS env var for external consumers (e.g., Grafana).
    import os
    cors_origins_str = os.environ.get("KANFEI_CORS_ORIGINS", "")
    cors_origins = [o.strip() for o in cors_origins_str.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

    # Read-only gate for public droplet mode.
    #
    # When ``station_driver_type == 'public_relay'`` (see
    # ``app/services/public_mode.py``), every state-mutating HTTP method
    # returns 403 unless the path is in the allowlist below.  The
    # allowlist holds the ingest endpoints — the ONLY writes a public
    # droplet legitimately accepts — and each is separately gated by
    # the ``require_ingest_secret`` bearer check in ``app/api/ingest.py``.
    #
    # Why middleware, not per-endpoint Depends: this gate must catch
    # write endpoints that are OPEN today (``/api/auth/login``,
    # ``/api/auth/setup-admin``, the bootstrap-bypass path in
    # ``/api/setup/*``) as well as any future OPEN write endpoint someone
    # forgets to gate.  A middleware at the outermost layer covers all
    # of them without a per-endpoint refactor.
    #
    # WebSocket coverage: today's WS channel is server-to-client only
    # (sensor broadcasts).  If a future feature adds inbound WS commands
    # that mutate state, they need their own gate — this HTTP middleware
    # will not catch them.
    app.state.public_mode_write_allowlist = frozenset({
        "/api/ingest/reading",
        "/api/ingest/config",
        "/api/ingest/backfill",
    })

    @app.middleware("http")
    async def public_mode_write_block(request: Request, call_next):
        if (request.method in {"POST", "PUT", "DELETE", "PATCH"}
                and request.url.path not in app.state.public_mode_write_allowlist
                and is_public_mode()):
            return JSONResponse(
                {"detail": "Kanfei is running in read-only public mode"},
                status_code=403,
            )
        return await call_next(request)

    # API routes
    app.include_router(api_router)

    # WebSocket
    app.websocket("/ws/live")(websocket_endpoint)

    # Custom background images directory (alongside the database)
    bg_dir = Path(settings.db_path).parent / "backgrounds"
    bg_dir.mkdir(parents=True, exist_ok=True)
    backgrounds_api.set_backgrounds_dir(bg_dir)
    app.mount("/backgrounds", StaticFiles(directory=str(bg_dir)), name="backgrounds")

    # Serve frontend static files if built
    frontend_dist = Path(__file__).parent.parent.parent / "frontend" / "dist"
    if frontend_dist.exists():
        # Mount hashed assets at /assets for correct MIME types
        assets_dir = frontend_dist / "assets"
        if assets_dir.exists():
            app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

        # SPA catch-all: serve the file if it exists, otherwise index.html.
        # `index.html` MUST NOT be heuristically cacheable — it is the only
        # non-hashed URL in the SPA and its body carries the current bundle's
        # hashed asset paths.  Without an explicit `Cache-Control`, browsers
        # apply RFC 9111 heuristic freshness (~10% of file age) and stop
        # revalidating; after a deploy the user's cached `index.html` still
        # references the previous deploy's `/assets/index-<hash>.js` and no
        # hard refresh of the SPA route fixes it.  The hashed asset paths
        # under `/assets/` are content-addressed and safe to cache long-term.
        index_html = frontend_dist / "index.html"
        _NO_CACHE = {"Cache-Control": "no-cache, must-revalidate"}

        @app.get("/{full_path:path}")
        async def serve_spa(full_path: str):
            file_path = frontend_dist / full_path
            if file_path.is_file():
                return FileResponse(str(file_path), headers=_NO_CACHE)
            return FileResponse(str(index_html), headers=_NO_CACHE)

    return app


# Application instance
app = create_app()

if __name__ == "__main__":
    import uvicorn

    # No basicConfig() here: configure_logging() at import time already did
    # it, and a second call is a no-op that only invites someone to "fix" it
    # by adding options that bypass the credential suppression (#206).
    uvicorn.run(app, host=settings.host, port=settings.port)

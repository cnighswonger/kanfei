"""FastAPI application factory and lifespan for Davis Weather Station.

The web application reads sensor data from SQLite and proxies hardware
commands to the logger daemon via IPC.  All serial/polling logic lives
in logger_main.py.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.responses import FileResponse

from .config import settings
from .models.database import init_database
from .ipc.client import IPCClient
from .ipc.dependencies import set_ipc_client
from .api.router import api_router
from .api import backgrounds as backgrounds_api
from .ws.handler import websocket_endpoint
from .services.log_buffer import install as install_log_buffer

# kanfei-nowcast is an optional add-on package.
try:
    from .services.nowcast_service import create_nowcast_service
    _NOWCAST_AVAILABLE = True
except ImportError:
    _NOWCAST_AVAILABLE = False

# Unified log format with timestamps for all loggers (app + uvicorn).
_LOG_FMT = "%(asctime)s %(levelname)-8s %(name)s - %(message)s"
_LOG_DATEFMT = "%Y-%m-%d %H:%M:%S"
logging.basicConfig(
    level=logging.INFO,
    format=_LOG_FMT,
    datefmt=_LOG_DATEFMT,
)
# Suppress noisy websockets library tracebacks on client disconnect (Windows semaphore timeout)
logging.getLogger("websockets").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


def _unify_uvicorn_log_format() -> None:
    """Override uvicorn's formatters so access/error logs match our format."""
    fmt = logging.Formatter(_LOG_FMT, datefmt=_LOG_DATEFMT)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        for handler in logging.getLogger(name).handlers:
            handler.setFormatter(fmt)


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

    # Construct nowcast service — remote mode is built-in, local requires
    # the optional kanfei-nowcast package.
    from .models.database import SessionLocal
    from .ws.handler import ws_manager
    from .services.nowcast.kanfei_adapters import (
        KanfeiConfigProvider,
        KanfeiStorageBackend,
        KanfeiEventEmitter,
    )
    from .services.nowcast import service_ref

    nc_config = KanfeiConfigProvider(SessionLocal)
    nc_storage = KanfeiStorageBackend(SessionLocal)
    nc_events = KanfeiEventEmitter(ws_manager)

    nowcast_task = None
    nowcast_mode = nc_config.get("nowcast_mode", "local")
    nowcast_enabled = nc_config.get_bool("nowcast_enabled", False)

    if nowcast_enabled and nowcast_mode == "remote":
        # Remote mode — built-in client, no kanfei-nowcast needed
        from .services.nowcast.remote_client import NowcastRemoteClient
        nc_service = NowcastRemoteClient(nc_config, nc_storage, nc_events)
        service_ref.nowcast_service = nc_service
        nowcast_task = asyncio.create_task(nc_service.start())
        logger.info("Nowcast mode: REMOTE (%s)", nc_config.get("nowcast_remote_url"))
    elif nowcast_enabled and _NOWCAST_AVAILABLE:
        # Local mode — kanfei-nowcast package installed
        nc_service = create_nowcast_service(nc_config, nc_storage, nc_events)
        service_ref.nowcast_service = nc_service
        # Also store in kanfei_nowcast.service for the full API module
        try:
            import kanfei_nowcast.service as _svc_mod
            _svc_mod.nowcast_service = nc_service
        except ImportError:
            pass
        nowcast_task = asyncio.create_task(nc_service.start())
        logger.info("Nowcast mode: LOCAL")
    elif nowcast_enabled:
        logger.warning(
            "Nowcast is enabled (mode=%s) but kanfei-nowcast package is not installed. "
            "Install kanfei-nowcast for local mode, or switch to remote mode in Settings.",
            nowcast_mode,
        )
    else:
        logger.info("AI nowcast not enabled")

    yield

    if nowcast_task is not None:
        nowcast_task.cancel()
    await client.close()
    logger.info("Application shutdown complete")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Kanfei Weather Station",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

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

        # SPA catch-all: serve the file if it exists, otherwise index.html
        index_html = frontend_dist / "index.html"

        @app.get("/{full_path:path}")
        async def serve_spa(full_path: str):
            file_path = frontend_dist / full_path
            if file_path.is_file():
                return FileResponse(str(file_path))
            return FileResponse(str(index_html))

    return app


# Application instance
app = create_app()

if __name__ == "__main__":
    import uvicorn

    logging.basicConfig(level=logging.INFO)
    uvicorn.run(app, host=settings.host, port=settings.port)

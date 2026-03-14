"""Top-level API router aggregation."""

import logging

from fastapi import APIRouter

from . import current, history, export, config, station, forecast, astronomy, output, setup, weatherlink, backgrounds, spray, usage, db_admin, logs

logger = logging.getLogger(__name__)

api_router = APIRouter(prefix="/api")

api_router.include_router(current.router)
api_router.include_router(history.router)
api_router.include_router(export.router)
api_router.include_router(config.router)
api_router.include_router(station.router)
api_router.include_router(forecast.router)
api_router.include_router(astronomy.router)
api_router.include_router(output.router)
api_router.include_router(setup.router)
api_router.include_router(weatherlink.router)
api_router.include_router(backgrounds.router)
api_router.include_router(spray.router)
api_router.include_router(usage.router)
api_router.include_router(db_admin.router)
api_router.include_router(logs.router)

# Nowcast API requires the optional kanfei-nowcast package.
try:
    from . import nowcast
    api_router.include_router(nowcast.router)
except ImportError:
    logger.info("Nowcast API endpoints not available (kanfei-nowcast not installed)")

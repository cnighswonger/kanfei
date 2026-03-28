"""Top-level API router aggregation."""

import logging

from fastapi import APIRouter

from . import current, history, export, config, station, forecast, astronomy, output, setup, weatherlink, backgrounds, spray, usage, db_admin, logs, backup, public_data, telegram, discord_bot as discord_bot_api, auth as auth_api

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
api_router.include_router(backup.router)
api_router.include_router(public_data.router)
api_router.include_router(telegram.router)
api_router.include_router(discord_bot_api.router)
api_router.include_router(auth_api.router)

# Nowcast API — full version requires kanfei-nowcast, lite version is built-in.
try:
    from . import nowcast
    api_router.include_router(nowcast.router)
    logger.info("Nowcast API: full (kanfei-nowcast installed)")
except ImportError:
    from . import nowcast_lite
    api_router.include_router(nowcast_lite.router)
    logger.info("Nowcast API: lite (remote mode only)")

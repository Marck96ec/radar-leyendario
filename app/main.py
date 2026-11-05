from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes.health import router as health_router
from app.api.routes.radar import router as radar_router
from app.core.logging import configure_logging
from app.core.settings import get_settings


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging(get_settings().LOG_LEVEL)
    yield


app = FastAPI(
    title="Radar Leyendario IA",
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(health_router)
app.include_router(radar_router, prefix="/api/v1/radar")

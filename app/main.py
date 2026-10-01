from fastapi import FastAPI

from app.api.routes.health import router as health_router
from app.api.routes.radar import router as radar_router


app = FastAPI(title="Radar Leyendario IA", version="0.1.0")
app.include_router(health_router)
app.include_router(radar_router, prefix="/api/v1/radar")

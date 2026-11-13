import logging
from fastapi import APIRouter, status
from pydantic import BaseModel
from app.config import settings
from app.database.connection import check_db_health

logger = logging.getLogger("filingguard.api.health")

router = APIRouter(tags=["Health"])


class HealthResponse(BaseModel):
    status: str
    app_env: str
    database: str
    version: str = "0.1.0"


@router.get("/health", response_model=HealthResponse, status_code=status.HTTP_200_OK)
def get_health() -> HealthResponse:
    """Return health status of API and database connection."""
    db_healthy = check_db_health()
    db_status = "connected" if db_healthy else "disconnected"

    if not db_healthy:
        logger.warning("Health check detected unhealthy database connection")

    return HealthResponse(
        status="healthy" if db_healthy else "degraded",
        app_env=settings.APP_ENV,
        database=db_status,
        version="0.1.0",
    )


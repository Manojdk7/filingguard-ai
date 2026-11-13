import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.api.routes.health import router as health_router
from app.api.routes.filings import router as filings_router
from app.api.routes.metrics import router as metrics_router
from app.api.routes.validations import router as validations_router
from app.api.routes.workflows import router as workflows_router
from app.api.routes.reviews import router as reviews_router
from app.api.routes.audit import router as audit_router
from app.api.routes.reports import router as reports_router
from app.database.connection import check_db_health
from app.database.models import init_db

# Configure root logging format
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("filingguard.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing FilingGuard AI Backend...")
    # Initialize SQLite database tables
    init_db()
    db_ok = check_db_health()
    logger.info(f"Database connection verified: {db_ok}")
    yield
    logger.info("Shutting down FilingGuard AI Backend...")


app = FastAPI(
    title="FilingGuard AI",
    description="Deterministic Financial Filing Integrity Engine",
    version="0.1.0",
    lifespan=lifespan,
)

# Serve the new HTML + Tailwind dashboard assets.
BASE_DIR = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# Configure CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled server error on {request.method} {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred.", "error": str(exc)},
    )


# Register routes
app.include_router(health_router)
app.include_router(filings_router)
app.include_router(metrics_router)
app.include_router(validations_router)
app.include_router(workflows_router)
app.include_router(reviews_router)
app.include_router(audit_router)
app.include_router(reports_router)


@app.get("/")
def root():
    return {
        "service": "FilingGuard AI",
        "status": "online",
        "environment": settings.APP_ENV,
        "docs_url": "/docs",
        "ui_url": "/ui",
    }


@app.get("/ui")
def dashboard_ui():
    return FileResponse(BASE_DIR / "static" / "dashboard.html")

"""FastAPI application — serves API + frontend static files."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.errors import register_exception_handlers
from app.api.patches import router as patches_router
from app.api.pipeline import router as pipeline_router
from app.api.products import router as products_router
from app.logging_config import setup

logger = logging.getLogger("app")

FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup()
    logger.info("OpsComm Pipeline starting up")
    yield
    logger.info("OpsComm Pipeline shutting down")


app = FastAPI(title="OpsComm Pipeline", lifespan=lifespan)

register_exception_handlers(app)

app.include_router(products_router)
app.include_router(patches_router)
app.include_router(pipeline_router)

if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")

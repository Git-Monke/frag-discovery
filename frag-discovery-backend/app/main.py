from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth.routes import router as auth_router
from app.config import get_settings
from app.db import create_all
from app.routes.data import router as data_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Dev bootstrap: create tables if missing (alembic migrations come later).
    create_all()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Fragrance Discovery API",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
    app.include_router(data_router, prefix="/api", tags=["data"])
    return app


app = create_app()


@app.get("/api/health", tags=["meta"])
def health() -> dict:
    return {"status": "ok"}

"""FastAPI backend for the AI Contract Assistant.

Run from the backend folder:
    uvicorn app.main:app --reload --port 8000
Interactive API docs: http://localhost:8000/docs
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import config, db
from .routers import contracts

app = FastAPI(
    title="AI Contract Assistant API",
    version="0.1.0",
    description="Contract list, original PDFs and (in a later step) the AI assistant.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.exception_handler(db.DatabaseNotReady)
async def database_not_ready(_: Request, exc: db.DatabaseNotReady) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.get("/health", tags=["meta"], summary="Liveness check")
def health() -> dict:
    return {"status": "ok", "database_ready": config.DB_FILE.exists()}


app.include_router(contracts.router)

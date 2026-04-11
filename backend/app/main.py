import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.core.errors import AppError

logger = logging.getLogger(__name__)

app = FastAPI(title="CloudMediaPilot API", version="0.1.0")
app.include_router(router)
app.mount(
    "/assets",
    StaticFiles(directory=Path(__file__).resolve().parent / "webui" / "assets"),
    name="assets",
)


@app.exception_handler(AppError)
async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.code, "message": exc.message},
    )


@app.exception_handler(Exception)
async def unknown_error_handler(_: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"code": "INTERNAL_ERROR", "message": "internal server error"},
    )

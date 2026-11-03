import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.logging import configure_logging
from app.core.rate_limit import InMemoryRateLimitMiddleware
from app.db.session import engine

settings = get_settings()
configure_logging()
logger = logging.getLogger("morrow.http")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Tenant-aware business operations API foundation.",
    docs_url="/docs" if settings.app_env.lower() != "production" else None,
    redoc_url="/redoc" if settings.app_env.lower() != "production" else None,
    lifespan=lifespan,
)
app.add_middleware(InMemoryRateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID", "Idempotency-Key"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "request failed", extra={"request_id": request_id, "path": request.url.path}
        )
        raise
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(self), geolocation=()"
    logger.info(
        "request complete",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": round((time.perf_counter() - start) * 1000, 2),
        },
    )
    return response


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    return JSONResponse(
        status_code=exc.status_code,
        headers={"X-Request-ID": getattr(request.state, "request_id", "")},
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "request_id": getattr(request.state, "request_id", None),
                "details": exc.details,
            }
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    errors = [
        {
            "location": list(error.get("loc", ())),
            "message": error.get("msg", "Invalid value"),
            "type": error.get("type", "value_error"),
        }
        for error in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        headers={"X-Request-ID": getattr(request.state, "request_id", "")},
        content={
            "error": {
                "code": "validation_error",
                "message": "Request validation failed",
                "request_id": getattr(request.state, "request_id", None),
                "details": errors,
            }
        },
    )


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(request: Request, exc: StarletteHTTPException):
    message = exc.detail if isinstance(exc.detail, str) else "The request could not be completed"
    return JSONResponse(
        status_code=exc.status_code,
        headers={**(exc.headers or {}), "X-Request-ID": getattr(request.state, "request_id", "")},
        content={
            "error": {
                "code": "http_error",
                "message": message,
                "request_id": getattr(request.state, "request_id", None),
            }
        },
    )


@app.exception_handler(SQLAlchemyError)
async def database_error_handler(request: Request, exc: SQLAlchemyError):
    logger.exception(
        "database operation failed",
        exc_info=exc,
        extra={"request_id": getattr(request.state, "request_id", None)},
    )
    return JSONResponse(
        status_code=500,
        headers={"X-Request-ID": getattr(request.state, "request_id", "")},
        content={
            "error": {
                "code": "database_error",
                "message": "A database operation failed",
                "request_id": getattr(request.state, "request_id", None),
            }
        },
    )


@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, exc: Exception):
    logger.exception(
        "unhandled application error",
        exc_info=exc,
        extra={"request_id": getattr(request.state, "request_id", None)},
    )
    return JSONResponse(
        status_code=500,
        headers={"X-Request-ID": getattr(request.state, "request_id", "")},
        content={
            "error": {
                "code": "internal_error",
                "message": "An unexpected error occurred",
                "request_id": getattr(request.state, "request_id", None),
            }
        },
    )


@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok", "service": settings.app_name}


@app.get("/health/ready", tags=["health"])
async def readiness():
    from fastapi import HTTPException

    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Database is not ready") from exc
    return {"status": "ready", "database": "ok"}


app.include_router(api_router, prefix=settings.api_v1_prefix)

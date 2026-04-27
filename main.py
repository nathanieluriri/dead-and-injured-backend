from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from core.config import get_settings
from core.rate_limit import limiter
from schemas.response_schema import APIError, APIResponse, ok_response

settings = get_settings()
app = FastAPI(title=settings.app_name, root_path=settings.root_path)
api_prefix = settings.api_prefix.rstrip("/")

app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RateLimitExceeded)
async def rate_limit_exceeded_handler(_: Request, exc: RateLimitExceeded) -> JSONResponse:
    error = APIError(code="rate_limited", message=f"Rate limit exceeded: {exc.detail}")
    content = APIResponse(
        success=False,
        message="Too many requests",
        data=None,
        meta=None,
        errors=[error],
    ).model_dump()
    return JSONResponse(status_code=429, content=content)


@app.exception_handler(HTTPException)
async def custom_http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
    error_message = exc.detail if isinstance(exc.detail, str) else "Request failed"
    error = APIError(code=f"http_{exc.status_code}", message=error_message)
    content = APIResponse(
        success=False,
        message=error_message,
        data=None,
        meta=None,
        errors=[error],
    ).model_dump()
    return JSONResponse(status_code=exc.status_code, content=content)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    errors = [
        APIError(
            code="validation_error",
            message=issue["msg"],
            field=".".join(str(part) for part in issue["loc"]),
        )
        for issue in exc.errors()
    ]
    content = APIResponse(
        success=False,
        message="Validation failed",
        data=None,
        meta=None,
        errors=errors,
    ).model_dump()
    return JSONResponse(status_code=422, content=content)


@app.exception_handler(Exception)
async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    content = APIResponse(
        success=False,
        message="Internal server error",
        data=None,
        meta=None,
        errors=[APIError(code="internal_error", message=str(exc))],
    ).model_dump()
    return JSONResponse(status_code=500, content=content)


@app.get("/", response_model=APIResponse[dict[str, str]])
def read_root() -> APIResponse[dict[str, str]]:
    return ok_response(data={"message": "Hello from FasterAPI!"}, message="API is running")


@app.get("/health", response_model=APIResponse[dict[str, str]])
@app.get("/healthz", response_model=APIResponse[dict[str, str]])
async def health_check() -> APIResponse[dict[str, str]]:
    return ok_response(data={"status": "healthy"}, message="Service is healthy")


@app.get("/readyz", response_model=APIResponse[dict[str, str]])
async def readiness_check() -> APIResponse[dict[str, str]]:
    return ok_response(data={"status": "ready"}, message="Service is ready")

# --- auto-routes-start ---
from api.v1.app_features import router as v1_app_features_router
from api.v1.game import router as v1_game_router
from api.v1.leaderboard import router as v1_leaderboard_router
from api.v1.match import router as v1_match_router
from api.v1.player import router as v1_player_router
from api.v1.scores import router as v1_scores_router
from api.v1.secret import router as v1_secret_router
from api.v1.user import router as v1_user_router

app.include_router(v1_app_features_router, prefix=api_prefix)
app.include_router(v1_game_router, prefix=api_prefix)
app.include_router(v1_leaderboard_router, prefix=api_prefix)
app.include_router(v1_match_router, prefix=api_prefix)
app.include_router(v1_player_router, prefix=api_prefix)
app.include_router(v1_scores_router, prefix=api_prefix)
app.include_router(v1_secret_router, prefix=api_prefix)
app.include_router(v1_user_router, prefix=api_prefix)
# --- auto-routes-end ---

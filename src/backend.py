import os
import secrets
from time import monotonic
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

SERVICE_VERSION = "0.1.0"
START_TIME = monotonic()

app = FastAPI(version=SERVICE_VERSION)
bearer_scheme = HTTPBearer(auto_error=False)


class AuthenticationError(Exception):
    """Raised when a request does not supply the configured API token."""


@app.exception_handler(AuthenticationError)
async def authentication_error_handler(
    request: Request,
    exc: AuthenticationError,
) -> JSONResponse:
    del request, exc
    return JSONResponse(
        status_code=401,
        content={
            "error": {
                "code": "unauthorized",
                "message": "A valid bearer token is required.",
            }
        },
        headers={"WWW-Authenticate": "Bearer"},
    )


async def require_bearer_token(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
) -> None:
    """Require the server-configured bearer token for versioned API routes."""
    expected_token = os.getenv("API_BEARER_TOKEN")
    supplied_token = credentials.credentials if credentials is not None else ""

    if (
        not expected_token
        or credentials is None
        or credentials.scheme.lower() != "bearer"
        or not secrets.compare_digest(supplied_token, expected_token)
    ):
        raise AuthenticationError


v1_router = APIRouter(
    prefix="/v1",
    dependencies=[Depends(require_bearer_token)],
)

@app.get(
    "/health",
    status_code=200
)
async def health() -> dict[str, str | int]:
    return {
        "status": "ok",
        "version": SERVICE_VERSION,
        "uptimeSeconds": int(monotonic() - START_TIME),
    }

@app.get(
    "/spec",
    tags=["Operations"],
    summary="Service capabilities",
    response_description="The supported providers and service limits.",
)
async def specification() -> dict:
    """Expose a machine-readable declaration of the service capabilities."""
    return {
        "specVersion": "1.0",
        "providers": ["mock", "llm"],
        "limits": {
            "maxPayloadBytes": 1048576,
            "chunkBytes": 65536,
            "maxConcurrentJobs": 4,
            "rateLimitPerMinute": 30,
        },
    }

@v1_router.get("/jobs")
async def list_jobs():
    return{"Jobs" : []}

@v1_router.post("/jobs")
async def create_jobs():
    return{"Status" : "Created"}


app.include_router(v1_router)

import os
import secrets
from pydantic import BaseModel, Field
from time import monotonic
from typing import Annotated, Literal
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

load_dotenv()

SERVICE_VERSION = "0.1.0"
START_TIME = monotonic()
ERROR_STATUS = {
    "unauthorized": 401,
    "payload_too_large": 413,
    "invalid_json": 400,
    "invalid_diff": 422,
    "idempotency_conflict": 409,
    "not_found": 404,
    "rate_limited": 429,
    "internal": 500,
}

class APIError(Exception):
    def __init__(self, code: str, message: str, *, headers: dict[str, str] | None = None) -> None:
        super().__init__(message) # so that the exection can keep the error msg
        self.code = code
        self.message = message
        self.status_code = ERROR_STATUS[code]
        self.headers = headers or {}

app = FastAPI(version=SERVICE_VERSION)
bearer_scheme = HTTPBearer(auto_error=False)

# Validation for options
class ReviewOptions(BaseModel):
    provider: Literal["mock", "llm"] = "mock"
    maxFindings: int = Field(gt=0, le=1000, default=100) # 0 < MaxFindings < 1000

# Validation for request
class ReviewRequest(BaseModel):
    diff: str = Field(min_length=1, default="")
    provider: Literal["mock", "llm"] = "mock"
    options: ReviewOptions = Field(default_factory=ReviewOptions) # used default factory so that each req get a clean obj

@app.exception_handler(APIError)
async def ApiErrorHandler(request : Request, exc : APIError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
        headers=exc.headers,
    )

# check for bearer token and compare it with the ones in env. Raised an error when the token is not the same or empty token
async def require_bearer_token( credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)]) -> None:
    expected_token = os.getenv("API_BEARER_TOKEN")
    supplied_token = credentials.credentials if credentials is not None else ""

    if ( not expected_token
        or credentials is None
        or credentials.scheme.lower() != "bearer"
        or not secrets.compare_digest(supplied_token, expected_token)):
        raise APIError("unauthorized", "A valid bearer token is required", headers={"WWW-Authenticate": "Bearer"})

# adds v1 to the route, each v1 path is req to provide an bearer token
v1_router = APIRouter(
    prefix="/v1",
    dependencies=[Depends(require_bearer_token)],
)

@app.get("/health", status_code=200, tags=["Operations"])
async def health() -> dict[str, str | int]:
    return {
        "status": "ok",
        "version": SERVICE_VERSION,
        "uptimeSeconds": int(monotonic() - START_TIME),
    }

@app.get("/spec", tags=["Operations"])
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

@v1_router.get("/jobs", tags=["Operations"])
async def list_jobs():
    return{"Jobs" : []}

@v1_router.post("/reviews", status_code=202, tags=["Operations"])
async def create_jobs(JobsReceived: ReviewRequest) -> dict:
    return{"Status" : "Created"}

app.include_router(v1_router)

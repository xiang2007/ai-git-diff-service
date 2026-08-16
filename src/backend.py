import asyncio
import logging
import os
import secrets
from uuid import uuid4
from src.errors import APIError
from pydantic import BaseModel, Field
from time import monotonic
from typing import Annotated, Literal
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, FastAPI, Request, BackgroundTasks
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from src.checkDiff import parse_diff
from src.mock_provider import run_mock_provider

logger = logging.getLogger(__name__)
load_dotenv()

MAX_PAYLOAD_BYTES = 1048576
SERVICE_VERSION = "0.1.0"
START_TIME = monotonic()
JOBS: dict[str, dict] = {}

app = FastAPI(version=SERVICE_VERSION)
bearer_scheme = HTTPBearer(auto_error=False)

# Validation for options
class ReviewOptions(BaseModel):
    provider: Literal["mock", "llm"] = "mock"
    maxFindings: int = Field(gt=0, le=1000, default=100) # 0 < MaxFindings < 1000

# Validation for request
class ReviewRequest(BaseModel):
    diff: str = Field(min_length=1)
    options: ReviewOptions = Field(default_factory=ReviewOptions) # used default factory so that each req get a clean obj

async def process_review(jobs_id : str, patch, provider : str, max_finding : int) -> None:
    job = JOBS[jobs_id]
    job["status"] = "running"
    try:
        if provider == "mock":
            all_findings = await asyncio.to_thread(run_mock_provider, patch)
        else:
            raise RuntimeError("LLM not configured") # haven't implemented llm
        job["findings"] = all_findings[:max_finding] # truncate the ordered results
        job["status"] = "done"
    except Exception:
        logger.exception("Review jobs %s failed", jobs_id)
        job["status"] = "failed"

@app.exception_handler(APIError)
async def ApiErrorHandler(request : Request, exc : APIError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
        headers=exc.headers,
    )

@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    del request
    errors = exc.errors()
    if any(e.get("type") == "json_invalid" for e in errors):
        return JSONResponse(
            status_code=400,
            content={"error": {"code": "invalid_json", "message": "Request body is not valid JSON."}},
        )
    message = (
        "diff is required and must be a non-empty string."
        if any("diff" in e.get("loc", ()) for e in errors)
        else "Invalid request body."
    )
    return JSONResponse(
        status_code=422,
        content={"error": {"code": "invalid_diff", "message": message}},
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
async def create_review(request: Request, payload: ReviewRequest, Background_tasks : BackgroundTasks) -> dict:
    if len(await request.body()) > MAX_PAYLOAD_BYTES:
        raise APIError("payload_too_large", "Request body exceeds 1 MiB.")
    patch = parse_diff(payload.diff) # parse the unified diff
    job_id = uuid4().hex
    JOBS[job_id] = {
        "jobId": job_id,
        "status": "queued",
        "findings": [],
        "usage": {
            "inputBytes": len(payload.diff.encode("utf-8")),
            "chunks": 1,
            "cacheHit": False,
        },
}
    Background_tasks.add_task( # append task to thread
        process_review,
        job_id,
        patch,
        payload.options.provider,
        payload.options.maxFindings,
    )
    return {"jobId": job_id, "status": "queued"}

@v1_router.get("/reviews/{job_id}", tags=["Operations"])
async def get_review(job_id: str) -> dict:
    job = JOBS.get(job_id)

    if job is None:
        raise APIError(
            "not_found",
            "Review job was not found.",
        )

    return job

app.include_router(v1_router)

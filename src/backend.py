import asyncio
import copy
import hashlib
import logging
import os
import secrets
from uuid import uuid4
from src.errors import APIError
from pydantic import BaseModel, Field
from time import monotonic
from typing import Annotated, Literal
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from contextlib import asynccontextmanager
from src.checkDiff import parse_diff
from src.mock_provider import run_mock_provider
from src.chunking import chunk_patch

logger = logging.getLogger(__name__)
load_dotenv()

type JobItem = tuple[
    str,   # job_id
    list,  # chunks
    str,   # provider
    int,   # max_findings
]

MAX_PAYLOAD_BYTES = 1048576
SERVICE_VERSION = "0.1.0"
START_TIME = monotonic()
JOBS: dict[str, dict] = {}
JOB_QUEUE: asyncio.Queue[JobItem] = asyncio.Queue()
RESULT_CACHE: dict[str, dict] = {}
IDEMPOTENCY_KEYS: dict[str, tuple[str, str]] = {}
JOB_REQUEST_HASHES: dict[str, str] = {}

async def worker() -> None:
    while True:
        job_id, chunks, provider, max_findings = await JOB_QUEUE.get()

        try:
            await process_review(
                job_id,
                chunks,
                provider,
                max_findings,
            )
        finally:
            JOB_QUEUE.task_done()

@asynccontextmanager
async def lifespan(app: FastAPI):
    del app

    workers = [
        asyncio.create_task(worker())
        for _ in range(4)
    ]

    try:
        yield
    finally:
        for worker_task in workers:
            worker_task.cancel()

        await asyncio.gather(
            *workers,
            return_exceptions=True,
        )

app = FastAPI(version=SERVICE_VERSION, lifespan=lifespan)
bearer_scheme = HTTPBearer(auto_error=False)

# Validation for options
class ReviewOptions(BaseModel):
    provider: Literal["mock", "llm"] = "mock"
    maxFindings: int = Field(gt=0, le=1000, default=100) # 0 < MaxFindings < 1000

# Validation for request
class ReviewRequest(BaseModel):
    diff: str = Field(min_length=1)
    options: ReviewOptions = Field(default_factory=ReviewOptions) # used default factory so that each req get a clean obj

async def process_review(job_id : str, chunks : list, provider : str, max_finding : int) -> None:
    job = JOBS[job_id]
    job["status"] = "running"
    try:
        if provider != "mock":
            raise RuntimeError("LLM not configured") # haven't implemented llm
        findById: dict[str, dict] = {}
        for chunk in chunks:
            chunkFindings = await asyncio.to_thread(run_mock_provider, chunk)
            for finding in chunkFindings:
                findById[finding["id"]] = finding
        allFindings = list(findById.values())
        allFindings.sort(key=lambda finding:(finding["path"], finding["line"], finding["ruleId"]))
        job["findings"] = allFindings[:max_finding]
        job["status"] = "done"

        request_hash = JOB_REQUEST_HASHES.pop(job_id, None)
        if request_hash is not None:
            RESULT_CACHE[request_hash] = {
                "findings": copy.deepcopy(allFindings),
                "usage": {
                    "inputBytes": job["usage"]["inputBytes"],
                    "chunks": job["usage"]["chunks"],
                },
            }
    except Exception:
        JOB_REQUEST_HASHES.pop(job_id, None)
        logger.exception("Review jobs %s failed", job_id)
        job["status"] = "failed"

@app.exception_handler(APIError)
async def ApiErrorHandler(request : Request, exc : APIError):
    del request
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
async def create_review(
    request: Request,
    payload: ReviewRequest,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict:
    raw_body = await request.body()
    if len(raw_body) > MAX_PAYLOAD_BYTES:
        raise APIError("payload_too_large", "Request body exceeds 1 MiB.")

    request_hash = hashlib.sha256(raw_body).hexdigest()

    if idempotency_key is not None:
        previous = IDEMPOTENCY_KEYS.get(idempotency_key)
        if previous is not None:
            previous_hash, previous_job_id = previous
            if previous_hash != request_hash:
                raise APIError(
                    "idempotency_conflict",
                    "Idempotency key was already used with a different request body.",
                )
            return {"jobId": previous_job_id, "status": "queued"}

    cached_result = RESULT_CACHE.get(request_hash)
    if cached_result is not None:
        job_id = uuid4().hex
        JOBS[job_id] = {
            "jobId": job_id,
            "status": "done",
            "findings": copy.deepcopy(cached_result["findings"])[
                :payload.options.maxFindings
            ],
            "usage": {
                "inputBytes": cached_result["usage"]["inputBytes"],
                "chunks": cached_result["usage"]["chunks"],
                "cacheHit": True,
            },
        }
        if idempotency_key is not None:
            IDEMPOTENCY_KEYS[idempotency_key] = (request_hash, job_id)
        return {"jobId": job_id, "status": "queued"}

    patch = parse_diff(payload.diff) # parse the unified diff
    chunks = chunk_patch(patch) # chunking
    job_id = uuid4().hex
    JOBS[job_id] = {
        "jobId": job_id,
        "status": "queued",
        "findings": [],
        "usage": {
            "inputBytes": len(payload.diff.encode("utf-8")),
            "chunks": len(chunks),
            "cacheHit": False,
        },
    }
    JOB_REQUEST_HASHES[job_id] = request_hash
    if idempotency_key is not None:
        IDEMPOTENCY_KEYS[idempotency_key] = (request_hash, job_id)
    await JOB_QUEUE.put(
        (
            job_id,
            chunks,
            payload.options.provider,
            payload.options.maxFindings,
        )
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

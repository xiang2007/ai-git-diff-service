from time import monotonic
from typing import Annotated
from fastapi import FastAPI, APIRouter, Depends
from fastapi.security import OAuth2PasswordBearer

SERVICE_VERSION = "0.1.0"
START_TIME = monotonic()

app = FastAPI(version=SERVICE_VERSION)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

v1_router = APIRouter(prefix='/v1')
app.include_router(v1_router)

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
            "maxPayloadBytes": 1_048_576,
            "chunkBytes": 65_536,
            "maxConcurrentJobs": 4,
            "rateLimitPerMinute": 30,
        },
    }

@v1_router.get("/jobs")
async def list_jobs(token: Annotated[str, Depends(oauth2_scheme)]):
    return{"Jobs" : []}

@v1_router.post("/jobs")
async def create_jobs():
    return{"Status" : "Created"}


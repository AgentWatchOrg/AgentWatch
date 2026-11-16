from dataclasses import dataclass

from fastapi import APIRouter

health_router: APIRouter = APIRouter(tags=["health"])


@dataclass(frozen=True)
class HealthResponse:
    status: str


@health_router.get("/health")
def get_health() -> HealthResponse:
    return HealthResponse(status="ok")

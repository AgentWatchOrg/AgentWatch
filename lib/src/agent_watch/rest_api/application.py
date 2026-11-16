from fastapi import FastAPI

from agent_watch.rest_api.routers.health_router import health_router


def create_application() -> FastAPI:
    created_application: FastAPI = FastAPI(title="AgentWatch API", version="0")
    created_application.include_router(health_router)
    return created_application


application: FastAPI = create_application()

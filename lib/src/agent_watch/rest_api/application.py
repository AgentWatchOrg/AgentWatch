import os

from fastapi import FastAPI

from agent_watch.logging_configuration import DEFAULT_LOG_LEVEL_NAME, LOG_LEVEL_ENVIRONMENT_VARIABLE, configure_logging
from agent_watch.rest_api.routers.health_router import health_router


def create_application() -> FastAPI:
    configure_logging(os.environ.get(LOG_LEVEL_ENVIRONMENT_VARIABLE, DEFAULT_LOG_LEVEL_NAME))
    created_application: FastAPI = FastAPI(title="AgentWatch API", version="0")
    created_application.include_router(health_router)
    return created_application


application: FastAPI = create_application()

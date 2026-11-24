import hmac
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import Field

from agent_watch.api.ingestion.event_store import EventStore, InMemoryEventStore
from agent_watch.api.ingestion.ingest_events import ingest_event_batch
from agent_watch.api.ingestion.models import EventValidator, IngestionBatchResult
from agent_watch.api.ingestion.schema_validator import load_telemetry_schema_validator
from agent_watch.rest_api.settings import INGESTION_API_KEY_ENVIRONMENT_VARIABLE, load_ingestion_api_key

MAXIMUM_EVENTS_PER_BATCH: int = 1000

ingestion_router: APIRouter = APIRouter(tags=["ingestion"])
shared_ingestion_event_store: InMemoryEventStore = InMemoryEventStore()


@dataclass(frozen=True)
class EventBatchRequest:
    events: Annotated[list[Any], Field(max_length=MAXIMUM_EVENTS_PER_BATCH)]


def require_ingestion_api_key(x_api_key: str = Header(default="")) -> None:
    expected_api_key: str | None = load_ingestion_api_key()
    if not expected_api_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Server misconfigured: {INGESTION_API_KEY_ENVIRONMENT_VARIABLE} is not set.")
    if not hmac.compare_digest(x_api_key.encode("utf-8"), expected_api_key.encode("utf-8")):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key.")


def get_ingestion_event_store() -> EventStore:
    return shared_ingestion_event_store


def get_telemetry_schema_validator() -> EventValidator:
    return load_telemetry_schema_validator()


@ingestion_router.post(
    "/v1/events", dependencies=[Depends(require_ingestion_api_key)],
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": "The X-Api-Key header is missing or incorrect."},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": f"The server has no {INGESTION_API_KEY_ENVIRONMENT_VARIABLE} configured."}})
def post_events(
        event_batch: EventBatchRequest, event_store: EventStore = Depends(get_ingestion_event_store),
        schema_validator: EventValidator = Depends(get_telemetry_schema_validator)) -> IngestionBatchResult:
    return ingest_event_batch(event_batch.events, schema_validator, event_store)

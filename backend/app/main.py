"""
AgentWatch backend ingestion prototype — spike #7.

Scope: demonstrate a minimal, functional interface that receives telemetry
from the forwarder, validates it against the draft v1 schema, and
accepts/rejects events individually without ever crashing the service on
bad input. This is a disposable prototype to inform the real D1/D2
implementation, not production code.

Run locally:
    export AGENTWATCH_API_KEY=dev-local-key
    uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

from typing import List

from fastapi import Depends, FastAPI
from pydantic import ValidationError

from app.auth import require_api_key
from app.schemas import EventBatch, IngestResult, RejectedEvent, TelemetryEvent
from app.storage import store

app = FastAPI(title="AgentWatch Ingestion Prototype", version="0.1.0-spike")


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


@app.post("/v1/events", response_model=IngestResult, dependencies=[Depends(require_api_key)])
def ingest_events(batch: EventBatch) -> IngestResult:
    """
    Accepts a batch of telemetry events.

    Per-event outcome, by design, instead of all-or-nothing:
    - A malformed event (wrong types/missing fields) is rejected with a
      recorded reason. It does not fail the whole batch or crash the service.
    - A duplicate event_id (already seen) is reported separately from
      malformed events, per D1's requirement to report missing, malformed,
      and duplicate events separately.
    """
    rejected: List[RejectedEvent] = []
    duplicate: List[RejectedEvent] = []
    accepted = 0

    for index, event in enumerate(batch.events):
        # FastAPI/pydantic already validated structural shape to build
        # `TelemetryEvent` objects here. We re-check cross-field coherence
        # (activity_type vs. details.activity_type) since that's not
        # expressible as a plain type constraint.
        coherence_errors = event.coherence_errors()
        if coherence_errors:
            rejected.append(
                RejectedEvent(index=index, event_id=event.event_id, reason="; ".join(coherence_errors))
            )
            continue

        if store.contains(event.event_id):
            duplicate.append(RejectedEvent(index=index, event_id=event.event_id, reason="duplicate event_id"))
            continue

        store.add(event)
        accepted += 1

    return IngestResult(accepted=accepted, rejected=rejected, duplicate=duplicate)


@app.post(
    "/v1/events/raw",
    response_model=IngestResult,
    dependencies=[Depends(require_api_key)],
)
def ingest_raw_events(payload: dict) -> IngestResult:
    """
    Same as /v1/events, but accepts a raw dict body instead of relying on
    FastAPI's request-model validation to reject the whole request.

    This exists to prove out malformed-event handling end-to-end: a batch
    containing JSON that doesn't even match the schema shape (missing
    required fields, wrong types) should still produce a 200 with per-event
    rejection reasons, rather than a blanket 422 that tells the forwarder
    nothing about *which* events were bad.
    """
    raw_events = payload.get("events", [])
    rejected: List[RejectedEvent] = []
    duplicate: List[RejectedEvent] = []
    accepted = 0

    for index, raw_event in enumerate(raw_events):
        event_id = raw_event.get("event_id") if isinstance(raw_event, dict) else None
        try:
            event = TelemetryEvent.model_validate(raw_event)
        except ValidationError as exc:
            rejected.append(RejectedEvent(index=index, event_id=event_id, reason=str(exc)))
            continue

        coherence_errors = event.coherence_errors()
        if coherence_errors:
            rejected.append(
                RejectedEvent(index=index, event_id=event.event_id, reason="; ".join(coherence_errors))
            )
            continue

        if store.contains(event.event_id):
            duplicate.append(RejectedEvent(index=index, event_id=event.event_id, reason="duplicate event_id"))
            continue

        store.add(event)
        accepted += 1

    return IngestResult(accepted=accepted, rejected=rejected, duplicate=duplicate)


@app.get("/v1/events/count")
def event_count() -> dict:
    """Debug-only endpoint for the prototype; not part of the proposed contract."""
    return {"count": store.count()}

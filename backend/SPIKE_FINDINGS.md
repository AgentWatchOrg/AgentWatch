# Spike #7 Findings: Backend Telemetry Ingestion Interface & Tech Stack

**Status:** Proposed solution, ready for team review.
**Code:** `backend/app/` (prototype), `backend/tests/test_ingestion.py` (demonstrates behavior).

## 1. Tech stack decision

**Confirmed: Python + FastAPI.** Reasons, validated by actually building this prototype rather than just reading docs:

- Pydantic (which FastAPI is built on) gives us schema validation almost for free — the v1 event schema in `app/schemas.py` *is* the validation logic, no separate hand-rolled checks needed.
- Request/response typing is enforced automatically and documented for free via FastAPI's generated OpenAPI docs (`/docs`).
- No blockers encountered at Sprint 1 scale. Revisit only if we hit concrete throughput limits during D4 performance testing.

Nothing in this exercise surfaced a reason to deviate from the roadmap's candidate choice.

## 2. Ingestion API contract (proposed)

```
POST /v1/events
Headers: X-API-Key: <shared-secret>
Body:    { "events": [ <TelemetryEvent>, ... ] }
Response (200): { "accepted": N, "rejected": [...], "duplicate": [...] }
```

- **Batched, not single-event.** The forwarder likely wants to send events in small batches rather than one HTTP call per event; batching is cheap for us to support and expensive to bolt on later.
- **Always HTTP 200 if the batch itself is well-formed JSON.** Per-event failures are data in the response, not HTTP errors. This matters because D2 requires rejecting bad events "without terminating the backend" — and without crashing the *batch* either. One bad event in a batch of 50 shouldn't cost us the other 49.
- **Three buckets in the response, matching D1's requirement to report missing/malformed/duplicate separately:**
  - `accepted` — count of events stored.
  - `rejected` — malformed events or schema-coherence failures, each with a reason.
  - `duplicate` — valid events whose `event_id` was already seen, reported separately from malformed (a duplicate isn't a data-quality problem, it's a delivery-retry artifact).

A secondary `/v1/events/raw` endpoint exists in the prototype purely to prove out the case where the incoming JSON doesn't even match the schema shape (missing fields, wrong types) — confirming we get per-event rejection reasons rather than FastAPI's default behavior of rejecting the *entire request* with a generic 422. This distinction matters enough that it should carry into the real implementation (see Open Questions).

## 3. Validation behavior

Two layers, both exercised by the tests:

1. **Structural validation** (pydantic): required fields, types, literal enums for `activity_type`/`source`/`outcome`.
2. **Coherence validation** (hand-written, `TelemetryEvent.coherence_errors()`): checks that don't reduce to a type — e.g. the top-level `activity_type` must match `details.activity_type`. Pydantic's union matching will happily accept a structurally-valid-but-semantically-mismatched event, so this check is necessary, not optional.

Both failure modes produce a rejection with a reason string; neither raises an unhandled exception.

## 4. Auth

Shared API key via `X-API-Key` header, checked against an environment variable. This is the deliberately minimal "good enough for Sprint 1" answer — one forwarder, one backend, low stakes while everything is still a prototype. See Open Questions for when this needs to grow up.

## 5. Persistence

**In-memory dict, keyed by `event_id`.** No database in Sprint 1. Rationale:

- Sprint 1's expected outcome is proving the pipeline (sensor → forwarder → backend → Splunk), not building durable storage.
- Splunk (D3) is the system of record for search/investigation; the backend doesn't need to duplicate that.
- Adding Postgres/Redis now would be solving a problem we don't have evidence for yet.

**Trade-off:** state resets on restart, and de-duplication only works within a single process's lifetime. Fine for Sprint 1 demos; explicitly called out below as a Sprint 2+ decision once the detection engine needs to correlate events over time.

## Open questions / follow-up tickets

- [ ] Does Sprint 2's detection engine need durable storage (events outlive a single process), or can it subscribe to a stream and stay stateless too? Decide before building D2.
- [ ] `/v1/events` (schema-validated) vs. `/v1/events/raw` (manual validation for per-event errors on malformed JSON) — pick one real contract instead of two prototype endpoints. Recommend keeping the raw-dict + manual `model_validate` approach as the real implementation, since it's the only one that gives per-event errors on structurally invalid input.
- [ ] Shared API key is fine for one forwarder; revisit (per-host tokens or mTLS) once more than one host is reporting telemetry.
- [ ] This prototype's schema (`app/schemas.py`) is a strawman for spike #6, not the final word — reconcile once #6 lands.
- [ ] No rate limiting / backpressure handling yet — out of scope for this spike, but worth a line in D4's limitations section.

## How to run this yourself

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest tests/ -v                                  # see accept/reject/duplicate behavior
AGENTWATCH_API_KEY=dev-local-key uvicorn app.main:app --reload   # run it for real, see /docs
```

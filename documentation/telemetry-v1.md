# v1 telemetry contract

**Canonical schema:** [AgentWatch v1 JSON Schema](schemas/agent-watch-v1.schema.json)

The contract is version `1.0`. Valid fixtures are in [documentation/fixtures/telemetry-v1/valid](https://github.com/AgentWatchOrg/AgentWatch/tree/main/documentation/fixtures/telemetry-v1/valid). Invalid examples are in [documentation/fixtures/telemetry-v1/invalid](https://github.com/AgentWatchOrg/AgentWatch/tree/main/documentation/fixtures/telemetry-v1/invalid).

## Event identity

The forwarder assigns `event_id` once, after normalization and redaction, as a SHA-256 hash of a canonical representation of the event: host, timestamp, process identity and lineage, activity type, target, and available type-specific details. The ID is stored with the event in the forwarder buffer. Replay resends the stored event unchanged, including `event_id` and `forwarder_seq`, so consumers deduplicate on `event_id`.

Two events with different canonical inputs never share an ID. If two distinct events produce the same canonical inputs, the forwarder adds the sensor thread ID or `forwarder_seq` to the canonical representation. This is safe because replay never recomputes the ID.

`forwarder_seq` is a positive integer that advances once for every event assigned an identity. It starts at 1 for a forwarder process and resets after a process restart. A gap within one forwarder process indicates lost delivery; a reset to 1 after a restart does not.

## Missing and unknown values

Sensor fields that are unavailable are omitted. The forwarder does not substitute an invented value.

Unknown session attribution is represented by:

```json
{
  "agent": {
    "attribution_status": "unknown",
    "session_id": null
  }
}
```

When attribution is known, `attribution_status` is `known` and `session_id` is a non-empty string.

The `process` object remains present because an event is impossible to attribute or correlate without it. Individual process fields are optional.

`outcome` is `success`, `denied`, or `unknown`. If a sensor does not provide a reliable return value, the forwarder sets `unknown`.

## Redaction

The forwarder removes credentials, secrets, environment variables, file contents, and unnecessary sensitive arguments before buffering or sending an event. Arguments longer than a fixed forwarder limit are truncated. It may set:

```json
{
  "redaction": {
    "applied": true,
    "rules": ["password-arg", "url-credential"]
  }
}
```

`rules` contains forwarder rule names. Redaction runs before `event_id` is assigned, so the ID never depends on removed values.

`permission` in `file_access` details is the Unix mode bits as a decimal integer, for example `420` for `0o644`.

## Field ownership

| Field | Supplied by |
|---|---|
| `schema_version` | Forwarder |
| `event_id`, `forwarder_seq` | Forwarder |
| `timestamp`, `host`, `source`, `process`, type-specific sensor details | Sensor, normalized by the forwarder |
| `activity_type`, `target`, `outcome` | Forwarder-derived from sensor fields |
| `agent` | Forwarder |
| `redaction` | Forwarder |

## Validation

Run the contract tests:

```bash
cd lib
python -m pip install -e ".[development]"
pytest tests/test_telemetry_contract.py
```

The test accepts every fixture under `documentation/fixtures/telemetry-v1/valid` and rejects every fixture under `documentation/fixtures/telemetry-v1/invalid`.

## Version changes

An additive optional field or new activity type is a MINOR change. A removed or renamed required field, a type or meaning change, or a new required field is a MAJOR change.

Consumers tolerate unknown fields in a MINOR version, and the v1 schema accepts every `1.x` `schema_version`. `activity_type` and `source` accept values added in a MINOR version; details are checked only for the known v1.0 activity types. The backend rejects an unsupported major version with a recorded reason. A MAJOR endpoint uses a new path such as `/v2/events`, and the backend accepts both the old and new major versions for one sprint before dropping the old one.

## Downstream consumers

- [Normalize and forward host telemetry](https://github.com/AgentWatchOrg/AgentWatch/issues/59)
- [Add validated telemetry ingestion](https://github.com/AgentWatchOrg/AgentWatch/issues/60)
- [Export accepted telemetry to Splunk](https://github.com/AgentWatchOrg/AgentWatch/issues/61)

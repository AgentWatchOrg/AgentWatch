# Local Splunk

The repository includes a Docker Compose service for running Splunk Enterprise locally as an HTTP Event Collector (HEC) target. It provides the Splunk backend described in the [architecture](../architecture.md).

The service uses the official `splunk/splunk:10.4` image on `linux/amd64`. On Apple Silicon, Docker Desktop runs this x86 image through emulation, which can be slower than a native image.

## Start Splunk

You need Docker with the Compose plugin. Create a local environment file and set a strong local admin password:

```bash
cd infrastructure/splunk
cp .env.example .env
```

Before starting the container, read and accept Splunk's applicable license and general terms. The Compose service passes the required acceptance flags to Splunk. Then start it:

```bash
docker compose up -d
docker compose logs -f splunk
```

Splunk can take a few minutes to initialize. Open [http://localhost:8000](http://localhost:8000) and sign in as `admin` with `SPLUNK_PASSWORD` from `.env`.

The local HEC endpoint is `https://localhost:8088/services/collector/event`. HEC uses the token in `SPLUNK_HEC_TOKEN`. Requests from another service on this Compose network can use `https://splunk:8088/services/collector/event`.

## Send a smoke-test event

The local HEC endpoint uses a self-signed certificate, so skip certificate verification for this local-only request:

```bash
curl -k https://localhost:8088/services/collector/event \
  -H "Authorization: Splunk $(grep '^SPLUNK_HEC_TOKEN=' .env | cut -d= -f2-)" \
  -H 'Content-Type: application/json' \
  -d '{"event":{"message":"AgentWatch local Splunk smoke test"},"sourcetype":"agentwatch:smoke"}'
```

A successful request returns `{"text":"Success","code":0}`. In Splunk Web, search for `sourcetype="agentwatch:smoke"` to find the event.

## Export AgentWatch telemetry

After `POST /v1/events` accepts events, the [web server](web-server.md) sends them to HEC in a background task. Rejected events and duplicates are never exported. Each HEC event carries the whole v1 event, with `sourcetype` `agentwatch:telemetry`, `source` `agentwatch:ingestion`, `host` from the event, and `time` from its `timestamp`. Each HEC request carries at most 100 events and 512 KB.

| Variable | Purpose |
|---|---|
| `AGENT_WATCH_SPLUNK_HEC_URL` | HEC base URL, for example `https://localhost:8088`. Export is off when unset. |
| `AGENT_WATCH_SPLUNK_HEC_TOKEN` | HEC token. Export is off when unset. |
| `AGENT_WATCH_SPLUNK_INDEX` | Index to write to. When unset, the token's default index (`main` locally). |
| `AGENT_WATCH_SPLUNK_HEC_VERIFY_TLS` | `false` skips certificate checks, for the local self-signed certificate only. |

A failed export logs `Splunk export failed: …` at error level without the token. The events wait in memory and are retried with the next batch the endpoint receives, even one that holds only duplicates. Only one export runs at a time; a batch that arrives during an export leaves its events for the next one, so a slow or unreachable Splunk ties up at most one worker thread. They are lost on restart. A batch Splunk rejects because of its data (HTTP 413, or 400 with HEC code 5, 6, 12, 13, or 15) is split until the bad event is found; that event is logged with its `event_id` and dropped.

The deployed web server has no Splunk settings yet, so it does not export.

Run the API against local Splunk and submit one fixture of each type:

```bash
cd lib
export AGENT_WATCH_INGESTION_API_KEY=local-key
export AGENT_WATCH_SPLUNK_HEC_URL=https://localhost:8088
export AGENT_WATCH_SPLUNK_HEC_TOKEN="$(grep '^SPLUNK_HEC_TOKEN=' ../infrastructure/splunk/.env | cut -d= -f2-)"
export AGENT_WATCH_SPLUNK_HEC_VERIFY_TLS=false
uvicorn agent_watch.rest_api.application:application --port 8001
```

```bash
jq -s '{events: .}' documentation/fixtures/telemetry-v1/valid/{process-exec,file-access,network-connect}.json \
  | curl -s http://localhost:8001/v1/events -H 'X-Api-Key: local-key' -H 'Content-Type: application/json' -d @-
```

Find an event by ID in Splunk Web:

```
sourcetype="agentwatch:telemetry" event_id="sha256:6f1d6a44"
| eval host=mvdedup(host)
| table _time host event_id activity_type target outcome agent.attribution_status agent.session_id
```

`host` and `source` each hold two values: one from the HEC metadata and one from the event itself, so `source` is both `agentwatch:ingestion` and the sensor name. `mvdedup` shows `host` once.

The fixture IDs are `sha256:6f1d6a44` (`process_exec`), `sha256:ab41fd22` (`file_access`), and `sha256:fe90cc11` (`network_connect`). Run `docker compose stop splunk` and submit a new event to see the export failure in the API log.

## Stop Splunk

Stop the container while keeping its data:

```bash
docker compose down
```

To also delete the locally persisted Splunk configuration and indexed data:

```bash
docker compose down --volumes
```

Keep `.env` private. The example HEC token is for local development only; do not reuse it for shared or deployed Splunk instances.

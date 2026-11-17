# Local Splunk

The repository includes a Docker Compose service for running Splunk Enterprise locally as an HTTP Event Collector (HEC) target. It provides the Splunk backend described in the [architecture](../architecture.md); it does not add an AgentWatch event producer or ingestion API.

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

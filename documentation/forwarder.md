# Forwarder

Turns Tetragon records into [v1 telemetry events](telemetry-v1.md) and sends them in batches to `POST /v1/events` on the [web server](infrastructure/web-server.md). Code: `lib/src/agent_watch/api/forwarder/`.

```bash
tetra getevents -o json > tetragon-events.json
agent-watch forwarder forward-tetragon-events \
  --tetragon-events-file tetragon-events.json \
  --ingestion-url http://52.60.176.146 \
  --ingestion-api-key "$INGESTION_API_KEY"
```

| Option | Env | Purpose |
|---|---|---|
| `--tetragon-events-file` | `TETRAGON_EVENTS_FILE` | Tetragon JSON export, one record per line; `-` reads stdin |
| `--ingestion-url` | `INGESTION_URL` | Base URL of the REST API |
| `--ingestion-api-key` | `INGESTION_API_KEY` | Sent as `X-Api-Key` |
| `--dry-run` | `IS_DRY_RUN` | Normalize and redact without sending |

The command exits `1` when the request fails or any event is rejected, and logs the reason for each rejection.

## Mapping

| Tetragon record | `activity_type` | `target` | `details` |
|---|---|---|---|
| `process_exec` | `process_exec` | `process.binary` | `arguments`, `cwd`, `parent_executable` from `parent.binary` |
| `process_kprobe` on `security_file_permission` or `security_file_open` | `file_access` | file path | `path`, `operation` from the access mask, `permission` from the mode text |
| `process_kprobe` on `tcp_connect` | `network_connect` | `daddr:dport` | `protocol`, `family`, `src_addr`, `src_port`, `dst_addr`, `dst_port` |

`process` comes from `process` (`exec_id`, `parent_exec_id`, `pid`, `binary`, `uid`) and `ppid` from `parent.pid`. `host` is `node_name` and `timestamp` is `time`. Only these fields are copied, so environment variables and file contents never enter an event. A kprobe `return` of `0` or more is `success`, `-1` or `-13` is `denied`, and anything else or no return value is `unknown`. Every other record type is skipped and counted. Attribution is always `unknown` until session correlation ([#5](https://github.com/AgentWatchOrg/AgentWatch/issues/5)) is built.

Raw inputs and the exact events they produce are in [documentation/fixtures/tetragon](https://github.com/AgentWatchOrg/AgentWatch/tree/main/documentation/fixtures/tetragon). They follow Tetragon's documented JSON export and are replaced by host samples from [#57](https://github.com/AgentWatchOrg/AgentWatch/issues/57) when those land. auditd fallback parsing waits for #57 to confirm which operations auditd covers.

## Redaction

Runs before `event_id` is assigned and before the event enters the buffer, on every text value in `details` and on `target`. Each rule replaces the secret with `*****` and is listed in `redaction.rules`.

| Rule | Matches |
|---|---|
| `authorization-header` | `Authorization: Bearer <value>`, `Basic`, `Token` |
| `secret-header` | a header whose name contains `password`, `secret`, `token`, `api-key`, or `access-key`, such as `X-Api-Key: <value>` |
| `password-arg` | a flag whose name contains `password`, `passwd`, `pwd`, `secret`, `token`, `api-key`, or `access-key`, followed by `=` or a space |
| `user-credential` | the password in `-u user:password` or `--user user:password` |
| `url-credential` | `user:password@` in a URL |
| `url-query` | a URL query string |
| `secret-assignment` | `NAME=value` where `NAME` contains `PASSWORD`, `PASSWD`, `_PWD`, `SECRET`, `TOKEN`, `API_KEY`, or `ACCESS_KEY` |
| `api-key` | `sk-…`, `github_pat_…`, `ghp_…`, `gho_…`, `ghs_…`, `ghu_…`, `AKIA…`, and `xox…-` keys |
| `argument-truncation` | `arguments` longer than 1024 characters |

## Delivery

`event_id` and `forwarder_seq` are assigned as the [contract](telemetry-v1.md#event-identity) describes. Events wait in an in-memory buffer keyed by `event_id` and are sent in batches of up to 1000. A failed request leaves them in the buffer, and the next send reuses the stored events, so the IDs do not change. After a response, accepted, duplicate, and rejected events leave the buffer. The buffer does not survive a restart.

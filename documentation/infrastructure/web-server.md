# Web server

FastAPI app in `lib/src/agent_watch/rest_api/` (package `agent_watch.rest_api`, extra `rest-api`), calling `agent_watch.api`. Every merge to main that passes `Test agent-watch library` is deployed.

- API: http://52.60.176.146
- Swagger: [http://52.60.176.146/docs](http://52.60.176.146/docs)
- OpenAPI schema: http://52.60.176.146/openapi.json

## Endpoints
| Method | Path | Returns |
|---|---|---|
| GET | `/health` | `{"status": "ok"}` |
| POST | `/github/webhooks` | Org webhook receiver. Verifies `X-Hub-Signature-256`, answers 202, then runs the [board sync](project-board.md#automation) for an AgentWatch issue opened, reopened, or closed, or a card added, edited, restored, or converted from a draft. Changes that arrive while a sync is already waiting are folded into it. `{"outcome": "pong" \| "synchronization started" \| "ignored"}`; 401 on a bad signature, 503 until its secrets are set. |

## Secrets
The server's secrets live only in GitHub repository secrets. Never set them in AWS by hand.

| Repository secret | Server variable | Holds |
|---|---|---|
| `BOARD_WEBHOOK_SECRET` | `GITHUB_WEBHOOK_SECRET` | Secret shared with the org webhook |
| `PROJECT_TOKEN` | `PROJECT_BOARD_TOKEN` | The same board token the rollover workflow uses |

On every deploy, `deploy-agent-watch-web-server.yml` mirrors them into SSM Parameter Store: it writes each one that is set and deletes the copy of each one that is not (SecureString, `/agent-watch/rest-api/<variable in kebab case>`), and the deploy script writes that path into `/etc/agent-watch/rest-api.env` for the service. The deploy role may only write that path and the instance role may only read it. Parameter Store is a relay, not a second copy to maintain: it is overwritten from GitHub on each deploy.

Settings with defaults, read from the service environment like the CLI's:

| Variable | Default |
|---|---|
| `PROJECT_OWNER` | `AgentWatchOrg` |
| `PROJECT_NUMBER` | `1` |
| `PROJECT_REPOSITORY` | `AgentWatchOrg/AgentWatch` |

Card changes in any other project are skipped and logged with both project IDs. Every sync logs how many changes it made: `journalctl -u agent-watch-web-server`.

Change a secret, then redeploy so the server picks it up:
```bash
gh secret set PROJECT_TOKEN -R AgentWatchOrg/AgentWatch
gh workflow run deploy-agent-watch-web-server.yml -R AgentWatchOrg/AgentWatch
```

## Board webhook
AgentWatchOrg has an org webhook for `Issues` and `Projects v2 items` that posts to `http://52.60.176.146/github/webhooks` with content type `application/json` and the `BOARD_WEBHOOK_SECRET` repository secret. It is the only thing that runs the board sync: there is no workflow or schedule for it. GitHub Actions cannot trigger on card changes, so the server runs the sync itself, one at a time, seconds after a change.

GitHub does not retry a failed delivery. If the server was down when something changed, redeliver it from the org's webhook settings (Recent Deliveries), or run the sync once from anywhere with a board token:
```bash
PROJECT_BOARD_TOKEN=$(gh auth token) agent-watch project-board synchronize-statuses
```

## Run locally
```bash
pip install -e "lib[development]"
uvicorn agent_watch.rest_api.application:application --reload
```
Swagger at http://127.0.0.1:8000/docs.

## Test
```bash
cd lib && mypy src tests && pytest
```
The REST API tests are part of `run_type_checks_and_unit_tests`, which runs on every PR and must pass to merge.

## Hosting
| Piece | Value |
|---|---|
| Stack | CloudFormation `agent-watch-web-server`, template `infrastructure/web-server/agent-watch-web-server-stack.yml` |
| Account, region | `786714620860`, `ca-central-1` |
| Instance | `t4g.nano`, Amazon Linux 2023, 1 GB swap, Elastic IP `52.60.176.146` |
| Access | Port 80 only. No SSH; use SSM Session Manager. |
| Service | systemd `agent-watch-web-server`, uvicorn on port 80, code in `/opt/agent-watch` |

## Deploy
After `Test agent-watch library` passes on main, `deploy-agent-watch-web-server.yml` assumes the stack's GitHub OIDC role and, through SSM, resets the instance's checkout to that commit and runs its `infrastructure/web-server/deploy_web_server.sh`: reinstall `lib[rest-api]`, install the systemd unit, restart. Repository variables `WEB_SERVER_*` hold the role, instance, region, and URL.

Redeploy without a code change:
```bash
gh workflow run deploy-agent-watch-web-server.yml -R AgentWatchOrg/AgentWatch
```

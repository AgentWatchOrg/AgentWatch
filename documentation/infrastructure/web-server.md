# Web server

FastAPI app in `lib/src/agent_watch/rest_api/` (package `agent_watch.rest_api`, extra `rest-api`), calling `agent_watch.api`. Every merge to main that passes `Test agent-watch library` is deployed.

- API: http://52.60.176.146
- Swagger: [http://52.60.176.146/docs](http://52.60.176.146/docs)
- OpenAPI schema: http://52.60.176.146/openapi.json

## Endpoints
| Method | Path | Returns |
|---|---|---|
| GET | `/health` | `{"status": "ok"}` |

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

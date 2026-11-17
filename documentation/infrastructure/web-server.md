# Web server

FastAPI app in `lib/src/agent_watch/rest_api/` (package `agent_watch.rest_api`, extra `rest-api`), calling `agent_watch.api`. Every merge to main that passes `Test agent-watch library` is deployed.

- API: http://52.60.176.146
- Swagger: [http://52.60.176.146/docs](http://52.60.176.146/docs)
- OpenAPI schema: http://52.60.176.146/openapi.json

## Endpoints
| Method | Path | Returns |
|---|---|---|
| GET | `/health` | `{"status": "ok"}` |

## Secrets
The server's secrets live only in GitHub repository secrets. Never set them in AWS by hand.

| Repository secret | Server variable | Holds |
|---|---|---|
| `BOARD_WEBHOOK_SECRET` | `GITHUB_WEBHOOK_SECRET` | Secret shared with the org webhook |
| `WEB_SERVER_PROJECT_BOARD_TOKEN` | `PROJECT_BOARD_TOKEN` | Fine-grained token: organization Projects read and write; AgentWatch repository only, Issues read |

On every deploy, `deploy-agent-watch-web-server.yml` mirrors them into SSM Parameter Store: it writes each one that is set and deletes the copy of each one that is not (SecureString, `/agent-watch/rest-api/<variable in kebab case>`), and the deploy script writes that path into `/etc/agent-watch/rest-api.env` for the service. The deploy role may only write that path and the instance role may only read it. Parameter Store is a relay, not a second copy to maintain: it is overwritten from GitHub on each deploy.

Change a secret, then redeploy so the server picks it up:
```bash
gh secret set WEB_SERVER_PROJECT_BOARD_TOKEN -R AgentWatchOrg/AgentWatch
gh workflow run deploy-agent-watch-web-server.yml -R AgentWatchOrg/AgentWatch
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

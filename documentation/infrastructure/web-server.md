# Web server

FastAPI server in `web-server/`, calling `agent_watch.api`. Not versioned: every merge to main that passes its tests is deployed.

- API: http://52.60.176.146
- Swagger: [http://52.60.176.146/docs](http://52.60.176.146/docs)
- OpenAPI schema: http://52.60.176.146/openapi.json

## Endpoints
| Method | Path | Returns |
|---|---|---|
| GET | `/health` | `{"status": "ok"}` |
| GET | `/project-board/status-synchronization-plan` | Changes the board sync would make (dry run) |
| GET | `/project-board/sprint-rollover-plan` | Next rollover plan and Sprint Log summary (dry run) |

Board endpoints return 503 until the `PROJECT_BOARD_TOKEN` is stored in SSM (see below).

## Run locally
```bash
pip install -e lib -e "web-server[development]"
PROJECT_BOARD_TOKEN=<token> uvicorn agent_watch_web_server.application:application --reload
```
Swagger at http://127.0.0.1:8000/docs.

## Test
```bash
cd web-server && mypy src tests && pytest
```
`run_web_server_type_checks_and_unit_tests` runs on every PR and must pass to merge.

## Hosting
| Piece | Value |
|---|---|
| Stack | CloudFormation `agent-watch-web-server`, template `infrastructure/web-server/agent-watch-web-server-stack.yml` |
| Account, region | `786714620860`, `ca-central-1` |
| Instance | `t4g.nano`, Amazon Linux 2023, 1 GB swap, Elastic IP `52.60.176.146` |
| Access | Port 80 only. No SSH; use SSM Session Manager. |
| Service | systemd `agent-watch-web-server`, uvicorn on port 80, code in `/opt/agent-watch` |
| Secrets | SSM parameter `/agent-watch/web-server/project-board-token` (SecureString), read on each deploy |

## Deploy
After `Test agent-watch web server` passes on main, `deploy-agent-watch-web-server.yml` assumes the stack's GitHub OIDC role and runs `infrastructure/web-server/deploy_web_server.sh <commit>` on the instance through SSM: pull, reinstall `lib` and `web-server`, restart. Repository variables `WEB_SERVER_*` hold the role, instance, region, and URL.

Store or rotate the token (scopes `project`, `repo`), then redeploy:
```bash
aws ssm put-parameter --profile joshuajipp --region ca-central-1 --type SecureString --overwrite \
  --name /agent-watch/web-server/project-board-token --value "$(pbpaste)"
gh workflow run deploy-agent-watch-web-server.yml -R AgentWatchOrg/AgentWatch
```

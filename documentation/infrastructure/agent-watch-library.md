# agent-watch library

Source: `lib/`. Not versioned: everything installs whatever is on `main`.

| Package | Contents |
|---|---|
| `agent_watch.api` | Core logic. Returns models, raises exceptions, never prints. Callable from the CLI or the REST API. |
| `agent_watch.cli` | `agent-watch` Click commands that call `api` and print results. |
| `agent_watch.rest_api` | FastAPI app that calls `api`; needs the `rest-api` extra. See [Web server](web-server.md). |

## Install
Into its own environment, from main:
```bash
python3.12 -m venv ~/.venvs/agent-watch
~/.venvs/agent-watch/bin/pip install "git+https://github.com/AgentWatchOrg/AgentWatch.git@main#subdirectory=lib"
```
The `pull-request-review review` command also needs the Claude Agent SDK:
```bash
~/.venvs/agent-watch/bin/pip install "agent-watch[pull-request-review] @ git+https://github.com/AgentWatchOrg/AgentWatch.git@main#subdirectory=lib"
```
For development:
```bash
pip install -e "lib[development]"
```

## Commands
| Command | Does |
|---|---|
| `agent-watch project-board synchronize-statuses` | Adds open issues to Backlog; sets or clears each card's sprint week from its status; marks closed issues Done |
| `agent-watch project-board roll-over-sprint` | Moves unfinished cards into the current sprint, adds future weeks, posts the Sprint Log summary |
| `agent-watch pull-request-review check-ticket-reference --pull-request-number <n>` | Fails unless the PR description has `Closes #N` or `Part of #N` for an existing issue. Runs on every PR as the required check `check_pull_request_references_a_ticket`. |

`project-board` options:

| Option | Env | Default |
|---|---|---|
| `--github-token` | `PROJECT_BOARD_TOKEN` | required (scopes `project`, `repo`) |
| `--project-owner` | `PROJECT_OWNER` | `AgentWatchOrg` |
| `--project-number` | `PROJECT_NUMBER` | `1` |
| `--repository` | `PROJECT_REPOSITORY` | `AgentWatchOrg/AgentWatch` |
| `--simulated-today` | `SIMULATED_TODAY` | today in Calgary |
| `--dry-run` | `IS_DRY_RUN` | off |

## Using the api from Python
```python
from datetime import date
from agent_watch.api.github_client import GitHubClient
from agent_watch.api.project_board.project_board_client import ProjectBoardClient
from agent_watch.api.project_board.synchronize_statuses import BoardChange, synchronize_statuses

client: ProjectBoardClient = ProjectBoardClient(GitHubClient(token), "AgentWatchOrg", 1, "AgentWatchOrg/AgentWatch")
changes: list[BoardChange] = synchronize_statuses(client, date.today(), is_dry_run=True)
```

## Test
```bash
cd lib && mypy src tests && pytest
```
`run_type_checks_and_unit_tests` runs on every PR and must pass to merge.

## Changes reaching workflows
Workflows install from `main` on every run, so a merged change is live on the next run. To undo one, revert it on `main`.

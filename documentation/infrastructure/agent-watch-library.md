# agent-watch library

Source: `lib/`. Released as a wheel on [GitHub Releases](https://github.com/AgentWatchOrg/AgentWatch/releases).

| Package | Contents |
|---|---|
| `agent_watch.api` | Core logic. Returns models, raises exceptions, never prints. Callable from the CLI or a REST API. |
| `agent_watch.cli` | `agent-watch` Click commands that call `api` and print results. |

## Install
Latest release:
```bash
gh release download --repo AgentWatchOrg/AgentWatch --pattern "agent_watch-*.whl" --dir agent-watch-release
pip install agent-watch-release/*.whl
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

## Release
1. Change code under `lib/src/`, with tests.
2. Bump `lib/VERSION` (semver) in the same PR.
3. Merge to main. `release-agent-watch-library.yml` tests, builds, and publishes release `v<VERSION>`.

Workflows install the latest release on every run.

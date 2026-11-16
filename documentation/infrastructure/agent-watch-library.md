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
~/.venvs/agent-watch/bin/pip install "agent-watch[claude-agent] @ git+https://github.com/AgentWatchOrg/AgentWatch.git@main#subdirectory=lib"
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

Every command takes `agent-watch --log-level DEBUG|INFO|WARNING|ERROR` (env `AGENT_WATCH_LOG_LEVEL`, default `INFO`). Output goes to stderr through the logger.

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

## Calling Claude
Every Claude call goes through `ClaudeAgentClient` in `agent_watch.api.claude_agent_client`. Install the `claude-agent` extra to use it.

```python
from pathlib import Path
from agent_watch.api.claude_agent_client import ClaudeAgentClient, ClaudeAgentConfiguration, ClaudeAgentResult

agent_client: ClaudeAgentClient = ClaudeAgentClient(ClaudeAgentConfiguration(
    model="claude-opus-5-5", maximum_turns=40, working_directory=Path("."),
    system_prompt_appendix="You triage AgentWatch detections.",
    output_schema={"type": "object", "properties": {"verdict": {"type": "string"}}, "required": ["verdict"]}))
result: ClaudeAgentResult = agent_client.run("Triage detection 17.")
```

| Setting | Default |
|---|---|
| `allowed_tools` | Read-only repository tools: `Read`, `Grep`, `Glob`, `git diff/log/show/blame` |
| `blocked_tools` | `Write`, `Edit`, `NotebookEdit`, `WebFetch`, `WebSearch` |
| `hidden_environment_variables` | `GITHUB_TOKEN` and `GH_TOKEN` blanked so the agent can't use them |
| Skills | Project skills in `.claude/skills/` are loaded |

`run` returns structured output (when `output_schema` is set), the final text, turn count, and cost, and raises `ClaudeAgentError` if the agent fails. Credentials come from `ANTHROPIC_API_KEY` or `CLAUDE_CODE_OAUTH_TOKEN`.

## Test
```bash
cd lib && mypy src tests && pytest
```
`run_type_checks_and_unit_tests` runs on every PR and must pass to merge.

## Changes reaching workflows
Workflows install from `main` on every run, so a merged change is live on the next run. To undo one, revert it on `main`.

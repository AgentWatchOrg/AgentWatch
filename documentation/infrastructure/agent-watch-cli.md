# agent-watch CLI

Source: `cli/`. Released as a wheel on [GitHub Releases](https://github.com/AgentWatchOrg/AgentWatch/releases).

## Install
Latest release:
```bash
gh release download --repo AgentWatchOrg/AgentWatch --pattern "agent_watch_cli-*.whl" --dir agent-watch-release
pip install agent-watch-release/*.whl
```
From source, for development:
```bash
pip install -e "cli[development]"
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

## Release
1. Change code under `cli/src/`.
2. Bump `cli/VERSION` (semver) in the same PR.
3. Merge to main. `release-agent-watch-cli.yml` builds the wheel and publishes release `v<VERSION>`.

Workflows install the latest release on every run, so a merged version bump is live on the next run.

## Check
```bash
mypy cli/src
python -m build --outdir built-cli-packages cli
```
`check-agent-watch-cli.yml` runs the same on every PR touching `cli/`.

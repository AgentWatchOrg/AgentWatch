---
name: following-existing-repository-patterns
description: Use before adding any new file, folder, module, dependency, workflow, script, abstraction, or convention to AgentWatch. Reuse and extend existing patterns; treat every new pattern as wrong until proven necessary.
---

# Following existing repository patterns

Consistency beats cleverness. Assume the repo already has a way to do what you need.

## Before writing anything new
1. Find the closest existing example: `git ls-files`, then read how similar code, scripts, workflows, skills, or docs are built.
2. Copy its structure, naming, error handling, configuration style, and file location.
3. Extend existing modules instead of adding parallel ones.

## Be skeptical of new patterns
A new pattern is any of: a new dependency, framework, top-level folder, file layout, config format, naming scheme, abstraction layer, or a second way to do something the repo already does.

Only introduce one when all are true:
- no existing pattern can do the job, even with a small extension
- you can say why in one sentence
- that sentence goes in the PR's **Why**

If unsure, ask the user before adding it. If an existing pattern is bad, don't work around it in one place: open a ticket to change it everywhere.

## Current patterns
| Thing | Pattern |
|---|---|
| Tooling and automation | A command group in the `agent-watch` Click CLI (`cli/src/agent_watch_cli/<group>/`), never a standalone script; typed, passes `mypy --strict` |
| Project board access | `ProjectBoardClient` in `cli/src/agent_watch_cli/project_board/project_board_client.py`; never a second GitHub client |
| Command configuration | Click options with an `envvar` named like the option; `--dry-run` supported for anything that changes state |
| CLI releases | Bump `cli/VERSION` on main; `release-agent-watch-cli.yml` publishes a GitHub release with the wheel |
| Workflows | Install the latest `agent-watch` release, then run one command; one job named after what it does; `workflow_dispatch` with `is_dry_run`; board token from `secrets.PROJECT_TOKEN` |
| Skills | `.claude/skills/<descriptive-name>/SKILL.md`, helper scripts beside it |
| Documentation | Markdown in `documentation/<area>/`, rules in `writing-project-documentation` |
| Issues and PRs | `creating-github-issues`, `writing-pull-request-descriptions`, `splitting-large-pull-requests-into-stacks` |

When a new pattern is accepted, add it to this table in the same PR.

## Before finishing
List every new file, dependency, and abstraction you added. For each, name the existing pattern it follows, or remove it.

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
| Python code | `lib/src/agent_watch/api/<area>/` for logic, `lib/src/agent_watch/cli/` for Click commands; see `structuring-library-code` |
| REST API | FastAPI in `web-server/src/agent_watch_web_server/`, one router per area calling `agent_watch.api`; Swagger at `/docs` |
| Infrastructure | CloudFormation in `infrastructure/<service>/`; deploys through SSM from GitHub Actions with an OIDC role, no SSH keys or AWS secrets in GitHub |
| GitHub access | `GitHubClient` in `api/github_client.py`; area clients like `ProjectBoardClient` wrap it; never a second HTTP client |
| Command configuration | Click options with an `envvar` named like the option; `--dry-run` supported for anything that changes state |
| Tests | pytest in `lib/tests/`, folders mirroring `src/agent_watch/`; shared fakes in `lib/tests/doubles/`; required check `run_type_checks_and_unit_tests` |
| Library releases | Bump `lib/VERSION` on main; `release-agent-watch-library.yml` tests and publishes a GitHub release with the wheel |
| Workflows | Scheduled automation installs the latest `agent-watch` release; PR checks install `./lib` from the PR; then run one command; one job named after what it does; `workflow_dispatch` with `is_dry_run`; board token from `secrets.PROJECT_TOKEN` |
| Skills | `.claude/skills/<descriptive-name>/SKILL.md`, helper scripts beside it |
| Documentation | Markdown in `documentation/<area>/`, rules in `writing-project-documentation` |
| Issues and PRs | `creating-github-issues`, `writing-pull-request-descriptions`, `splitting-large-pull-requests-into-stacks` |
| Claude agents | Claude Agent SDK with `ANTHROPIC_API_KEY` or `CLAUDE_CODE_OAUTH_TOKEN` from repository secrets, wrapped in an `api` client class; read-only tools, `max_turns` cap, structured output parsed into models; skills from `main` |
| Pull request review | `review-pull-requests-with-claude.yml` runs `agent-watch pull-request-review review`; rules in `reviewing-pull-requests-as-senior-staff-engineer` |

When a new pattern is accepted, add it to this table in the same PR.

## Before finishing
List every new file, dependency, and abstraction you added. For each, name the existing pattern it follows, or remove it.

# RoboReviewer

RoboReviewer, a Claude agent, reviews every pull request into `main` at senior staff level and posts its findings as review comments. It runs on Claude Opus 5.5 through the Claude Agent SDK, from `agent-watch pull-request-review review`.

## Identity
RoboReviewer posts as its own GitHub App, with the avatar in `assets/robo-reviewer/robo-reviewer-avatar.png`. Until the app is configured, it posts as `github-actions`.

Configured: app `agentwatch-roboreviewer` (App ID `5779453`), installed on this repository only. To recreate it, an org owner does:
1. **AgentWatchOrg → Settings → Developer settings → GitHub Apps → New GitHub App.**
2. Name `AgentWatch RoboReviewer` (app names are unique across GitHub). Homepage: the repository URL. Uncheck **Webhook → Active**.
3. Repository permissions: **Contents** read, **Issues** read and write, **Pull requests** read and write. Metadata read is added automatically.
4. **Where can this app be installed:** only this account. Create it.
5. On the app page, upload `robo-reviewer-avatar.png` under **Display information**. Then **Credentials → Key pairs → New key** (downloads a `.pem`).
6. **Install App** → AgentWatchOrg → only `AgentWatch`.
7. Store the app ID and key:
   ```bash
   gh variable set ROBO_REVIEWER_APP_ID -R AgentWatchOrg/AgentWatch --body <app id>
   gh secret set ROBO_REVIEWER_PRIVATE_KEY -R AgentWatchOrg/AgentWatch < path/to/key.pem
   ```
   Delete the `.pem` afterwards.

A summary comment already posted by `github-actions` can't be edited by the app; delete it once and RoboReviewer posts a new one.

## When it runs
`review-pull-requests-with-claude.yml` runs on `opened`, `reopened`, `ready_for_review`, and every push (`synchronize`) to a pull request whose base is `main`. Drafts are skipped until marked ready. A newer push cancels a review still running for the same pull request.

It only comments. Unresolved comments block the merge through main's required conversation resolution.

## What it checks
The agent follows `.claude/skills/reviewing-pull-requests-as-senior-staff-engineer`:

1. Reads the pull request, its ticket, and every changed file in full.
2. Reads every repository skill and checks the change against them.
3. Runs Claude Code's `code-review` skill as the bug-finding pass.
4. Keeps only findings it can tie to a concrete failure scenario or a written repository rule.

The skills come from `main`, never from the pull request, so a pull request cannot loosen its own review. The agent can only read files and run `git diff`, `git log`, `git show`, and `git blame`. It stops after 150 turns.

| Severity | Meaning |
|---|---|
| Critical | Data loss, security hole, broken main, CI, or deployment |
| High | Likely bug in normal use, or a clear repository skill violation |
| Medium | Edge-case bug, missing test, or costly design |
| Low | Minor issue or small documentation gap |

Categories: `correctness`, `security`, `performance`, `reliability`, `testing`, `repository_guidelines`, `maintainability`, `documentation`, `other`.

## Comments
| Finding location | Posted as |
|---|---|
| Lines in the diff | Inline comment, all in one review |
| Changed file, lines outside the diff | File comment |
| File the pull request does not change | Listed in the summary comment |

One summary comment per pull request is edited in place on every run.

## No duplicate comments
Each finding comment carries a hidden fingerprint of its path, category, and title. Before posting, the reviewer drops any finding that:

- has a fingerprint already on the pull request, whether its thread is open, resolved, or outdated
- has the same category as an earlier reviewer comment within 3 lines of it

The agent also sees every existing comment, including human ones, and is told not to raise anything they cover. Resolving a thread is final: the reviewer never raises that finding again.

## Setup
One repository secret, whichever you have:

| Secret | From |
|---|---|
| `ANTHROPIC_API_KEY` | An API key from console.anthropic.com, billed per token |
| `CLAUDE_CODE_OAUTH_TOKEN` | `claude setup-token`, using a Claude subscription's limits |

```bash
gh secret set ANTHROPIC_API_KEY -R AgentWatchOrg/AgentWatch
```

Without either secret the job stops after its first step and posts nothing. Repository variable `PULL_REQUEST_REVIEWER_MODEL` overrides the model (default `claude-opus-5-5`).

## Run it by hand
```bash
gh workflow run review-pull-requests-with-claude.yml -R AgentWatchOrg/AgentWatch -f pull_request_number=<number> -f is_dry_run=true
```

Locally, from a checkout of the pull request head, with `ANTHROPIC_API_KEY` exported or `claude auth login` done:
```bash
GITHUB_TOKEN=$(gh auth token) agent-watch pull-request-review review --pull-request-number <number> --dry-run
```

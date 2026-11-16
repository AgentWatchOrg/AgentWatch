# Pull request reviewer

A Claude agent reviews every pull request into `main` at senior staff level and posts its findings as review comments. It runs on Claude Opus 5.5 through Amazon Bedrock, using the Claude Agent SDK, from `agent-watch pull-request-review review`.

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
| Piece | Value |
|---|---|
| Stack | CloudFormation `agent-watch-pull-request-reviewer`, template `infrastructure/pull-request-reviewer/pull-request-reviewer-stack.yml` |
| Access | GitHub OIDC role allowed only `bedrock:InvokeModel*` on Anthropic models |
| Repository variables | `PULL_REQUEST_REVIEWER_ROLE_ARN`, `PULL_REQUEST_REVIEWER_AWS_REGION` (`us-east-1`), optional `PULL_REQUEST_REVIEWER_MODEL` |

The workflow does nothing until `PULL_REQUEST_REVIEWER_ROLE_ARN` is set. Claude Opus 5.5 model access must be enabled in the Bedrock console.

```bash
aws cloudformation deploy --region ca-central-1 --stack-name agent-watch-pull-request-reviewer \
  --template-file infrastructure/pull-request-reviewer/pull-request-reviewer-stack.yml \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides GitHubActionsOidcProviderArn=arn:aws:iam::786714620860:oidc-provider/token.actions.githubusercontent.com
```

## Run it by hand
```bash
gh workflow run review-pull-requests-with-claude.yml -R AgentWatchOrg/AgentWatch -f pull_request_number=<number> -f is_dry_run=true
```

Locally, from a checkout of the pull request head, with AWS credentials that can call Bedrock:
```bash
CLAUDE_CODE_USE_BEDROCK=1 AWS_REGION=us-east-1 GITHUB_TOKEN=$(gh auth token) \
  agent-watch pull-request-review review --pull-request-number <number> --dry-run
```

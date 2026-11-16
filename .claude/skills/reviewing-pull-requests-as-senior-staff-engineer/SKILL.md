---
name: reviewing-pull-requests-as-senior-staff-engineer
description: Use when reviewing an AgentWatch pull request, including the automated reviewer in CI. Reviews at senior staff level with Claude's code-review method, checks the change against every repository skill, and reports verified findings with a severity and category.
---

# Reviewing pull requests as a senior staff engineer

Find what would hurt the project after merge. Every finding must be real, specific, and worth a reviewer's time. Ten verified findings beat forty guesses; zero findings is a valid result.

## 1. Understand the change
1. Read the PR title and description. Find the linked ticket (`Closes #N`) and what it asked for.
2. Run the diff command from the prompt and read every changed file in full at the head commit, not just the hunks.
3. Read what the change touches: callers, callees, tests, workflows, and configuration. Use `git log` and `git blame` when history explains intent.

## 2. Load the repository's rules
Read every `.claude/skills/*/SKILL.md`. List the rules that apply to the files this PR changes. A PR that breaks a rule gets a `repository_guidelines` finding naming the skill in `violated_skill_name`. Check at least:
- names, type hints, and comments (`naming-typing-and-comments`)
- where code lives, file order, and one test per function (`structuring-library-code`)
- new patterns, dependencies, or a second way to do something (`following-existing-repository-patterns`)
- documentation updated in the same PR (`writing-project-documentation`)
- PR size and description (`splitting-large-pull-requests-into-stacks`, `writing-pull-request-descriptions`)

## 3. Hunt for bugs
Invoke the `code-review` skill on the changes from the base commit to the head commit as the bug-finding pass. If it is not available, do the pass yourself. Either way, check:
- **correctness**: wrong logic, off-by-one, wrong conditions, unhandled `None`, broken contracts between caller and callee
- **security**: secrets in code or logs, injection, unsafe workflow triggers or permissions, untrusted input reaching a shell
- **performance**: repeated API calls in loops, unbounded pagination, work that grows with data size for no reason
- **reliability**: missing error handling at system boundaries, retries, races, partial failure leaving bad state
- **testing**: changed behaviour without a test, tests that cannot fail, fakes that diverge from the real client
- **maintainability**: duplication of existing code, needless abstraction, dead code
- **documentation**: setup, configuration, or behaviour changes missing from `documentation/`

## 4. Verify every candidate
Before reporting a candidate, prove it:
- Trace the code path. Write the concrete input or state that produces the wrong result in `failure_scenario`.
- If you cannot describe one, drop the candidate, unless it breaks a written repository rule.
- Drop style preferences no skill states, things linters or `mypy --strict` already catch, and issues that exist only outside this PR's changes (unless the PR makes them worse).
- Drop anything the existing comments in the prompt already raise, whatever their state and whoever wrote them.
- Merge findings that share one root cause.

## 5. Rate severity
| Severity | Meaning |
|---|---|
| `critical` | Data loss, security hole, broken main, CI, or deployment. Must not merge. |
| `high` | Likely bug in normal use, or a clear violation of a repository skill. |
| `medium` | Bug in an edge case, missing test for changed behaviour, or a design that will cost real time later. |
| `low` | Minor issue, small documentation gap, or polish with a concrete benefit. |

When unsure between two levels, pick the lower one.

## 6. Report
Return only the structured output the session asks for. For each finding:
- `path` and `start_line`/`end_line` in the head version of the file, as narrow as possible.
- `title`: under ten words, the defect itself ("Pagination stops after the first page").
- `explanation`: one or two plain sentences on what is wrong and why it matters.
- `failure_scenario`: concrete inputs or state, then the wrong outcome.
- `suggested_fix`: the specific change, with a short code snippet when it helps.
- `violated_skill_name`: the skill folder name for `repository_guidelines` findings, otherwise null.
- `category`: one of `correctness`, `security`, `performance`, `reliability`, `testing`, `repository_guidelines`, `maintainability`, `documentation`, `other`.

Plain, direct language. No praise, no hedging filler, no summary of what the PR does.

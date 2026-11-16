---
name: splitting-large-pull-requests-into-stacks
description: Use before opening or pushing any AgentWatch pull request, and when planning a change that may grow large. PRs over 500 changed lines must be split into a stack of smaller PRs.
---

# Splitting large pull requests into stacks

No PR over 500 changed lines (additions + deletions). Split bigger work into a stack: a chain of PRs where each one builds on the one below it.

## Check size before opening a PR
```bash
git fetch origin
git diff --shortstat origin/main...HEAD
```
Lockfiles and generated files don't count. Everything else does.

If it's over 500, don't open the PR. Split it first. If a change is planned to be large, plan the stack before writing code.

## How to split
Each PR in the stack:
- does one thing and makes sense reviewed on its own
- leaves main working if merged alone (builds, tests pass)
- stays under 500 lines

Typical order: schema/interfaces → core logic → wiring/integration → documentation. Tests go in the same PR as the code they test.

## Build the stack
```bash
git checkout -b feat/hec-1-schema origin/main      # commit part 1
git push -u origin feat/hec-1-schema
gh pr create --base main ...

git checkout -b feat/hec-2-client                  # from part 1, commit part 2
git push -u origin feat/hec-2-client
gh pr create --base feat/hec-1-schema ...
```
Each PR's base is the branch below it, so reviewers see only that PR's diff.

## PR descriptions
Follow the `writing-pull-request-descriptions` skill, with two changes:
- Only the top PR says `Closes #N`. The others say `Part of #N`, so the ticket stays open until the last piece merges.
- Add one line under it:
```
Stack 2/3, on top of #41
```

## Merging
Merge bottom-up. After the bottom PR merges (squash), rebase the next branch onto main and retarget it:
```bash
git fetch origin
git rebase --onto origin/main feat/hec-1-schema feat/hec-2-client
git push --force-with-lease
gh pr edit <next-pr> --base main
```

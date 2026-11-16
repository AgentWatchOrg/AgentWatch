# Stacked pull requests

Changes over 500 lines ship as a stack: a chain of pull requests where each one builds on the one below.

## Branch layout
```
main
 └─ feature/part-1   → base: main
     └─ feature/part-2 → base: feature/part-1
         └─ feature/part-3 → base: feature/part-2
```
Each pull request shows only its own diff.

## Merge order
Merge bottom-up. After a pull request merges, rebase the next branch onto `main` and retarget it:
```bash
git rebase --onto origin/main feature/part-1 feature/part-2
git push --force-with-lease
gh pr edit <next pull request> --base main
```

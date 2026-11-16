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

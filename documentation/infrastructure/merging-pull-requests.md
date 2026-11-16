# Merging pull requests

`main` accepts a pull request when all of these hold. They apply to admins too.

| Requirement | Source |
|---|---|
| `run_type_checks_and_unit_tests` passes | `test-agent-watch-library.yml` |
| `check_pull_request_references_a_ticket` passes | `check-pull-request-ticket-reference.yml` |
| 1 approving review | Branch protection |
| Every conversation resolved | Branch protection |

## Bypassing with a label
A repository admin can add the `bypass-merge-requirements` label to skip the checks and the approval:

1. `bypass-merge-requirements-with-label.yml` checks who added the label. If they are an admin, GitHub Actions approves the pull request.
2. Both required check workflows rerun on the label change, see the admin's label, and pass without running.

If anyone else adds the label, the workflow removes it and nothing is skipped. Removing the label dismisses the Actions approval and the checks run for real again. Unresolved conversations still block the merge.

The checks read the label through `agent-watch` installed from `main`, so a pull request cannot change its own bypass rule.

```bash
gh pr edit <number> -R AgentWatchOrg/AgentWatch --add-label bypass-merge-requirements
```

GitHub Actions may approve pull requests because "Allow GitHub Actions to create and approve pull requests" is on for the organization and the repository.

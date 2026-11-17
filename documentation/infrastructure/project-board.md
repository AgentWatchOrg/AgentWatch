# Project board

[AgentWatch Board](https://github.com/orgs/AgentWatchOrg/projects/1)

## Views
| View | Shows |
|---|---|
| Backlog | Every card in Backlog, grouped by priority. Not in any sprint. |
| Sprint Board | All cards in the current sprint, by status. |
| My Sprint Board | Your cards in the current sprint. |

## Statuses
| Status | Sprint |
|---|---|
| Backlog | None |
| Ready, In Progress, Blocked, Done | Current week |

Sprints are one week, Monday to Sunday. Winter break (Dec 14 – Jan 3) has no sprints.

## Automation
| When | What happens | Run by |
|---|---|---|
| Issue opened | Added to the board in Backlog | The web server's [board webhook](web-server.md#board-webhook), running `synchronize_statuses` seconds after the change |
| Card moved out of Backlog | Put in the current sprint | same |
| Card moved back to Backlog | Removed from its sprint | same |
| Issue closed | Status set to Done | same |
| Monday 00:00 | Unfinished cards move to the new sprint; summary posted on the Sprint Log issue | `weekly-sprint-rollover.yml` (`agent-watch project-board roll-over-sprint`) |

The rollover workflow needs the `PROJECT_TOKEN` repository secret (scopes `project`, `repo`). The web server uses its own narrower `project-board-token` from SSM.

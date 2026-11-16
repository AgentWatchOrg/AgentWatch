---
name: create-ticket
description: Use whenever creating a GitHub issue/ticket for AgentWatch. Writes a short title and a 1-3 sentence why, sets priority, and adds it to the AgentWatch Board.
---

# Create a ticket

Short beats complete. If unsure whether to include something, leave it out.

## Title
- Under ~60 characters, imperative: "Add HEC export retry", "Spike: Tetragon vs auditd".
- No prefixes like "[Feature]", no trailing period.

## Body
1-3 plain sentences on **why** this needs doing. Nothing else.
- No headings, bullet lists, checklists, acceptance criteria, implementation plans, or "Context/Background" sections.
- No filler or mannered prose ("This ticket aims to...", "It is important to note...", "In order to ensure..."). State the reason directly.
- No AI attribution or sign-off.

Example body:
> Backend drops events when Splunk is down for a few seconds, so D3 latency tests fail. Need bounded retry on HEC export.

## Priority
Pick one, don't ask unless there's no signal at all:
- `p0` blocks others or a deadline this week
- `p1` needed for the current milestone
- `p2` normal (default)
- `p3` nice to have
- `p4` someday

## Labels
Always exactly one type label, plus 1-2 area labels that fit. Use only these.

Type:
- `feature` new functionality
- `bug` something broken
- `spike` time-boxed research or a decision
- `test` validation runs, test records
- `documentation` docs, reports, deployment guide

Area:
- `sensor` eBPF/Tetragon, auditd
- `forwarder` host-side filtering, attribution, delivery
- `backend` ingestion API, event schema, validation
- `detection` rules, correlation, detection records
- `splunk` HEC export, searches, dashboards, observability
- `agent` Claude Code / monitored agents, session attribution
- `infra` VMs, deployment, CI/CD
- `eval` evaluation harness, scenarios, metrics, demo replay

## Create it
```bash
.claude/skills/create-ticket/create.sh "<title>" <p0-p4> <type,area[,area]> <<'EOF'
<body>
EOF
```
This creates the issue with its priority and labels, adds it to the board as Backlog with Priority set, and prints the URL. Reply with just the URL.

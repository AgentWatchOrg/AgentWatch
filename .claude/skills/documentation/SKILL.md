---
name: documentation
description: Use whenever a change in AgentWatch adds or changes something non-trivial (component, API, schema, config, deployment step, detection rule, Splunk setup, spike decision), and whenever writing or editing anything under docs/. Keeps the GitHub Pages docs current, concise, and free of bloat.
---

# Documentation

Docs live in `docs/` as Markdown and publish to https://agentwatchorg.github.io/AgentWatch/ on every merge to main.

## When to document
Update docs in the same PR as the change when it adds or changes:
- a component, API endpoint, or interface between components
- the event schema or detection record format
- configuration, environment variables, or required privileges
- a deployment, setup, or test-run step
- a detection rule or evaluation scenario
- Splunk indexes, sourcetypes, searches, or dashboards
- a decision from a spike (what was chosen and why)

Skip docs for refactors, renames, typo fixes, and anything a reader would not need to run, integrate with, or understand the system.

## Where
One folder per area, matching the issue area labels. Create a folder only when its first page is written; the nav builds itself from the folders.

| Folder | Content |
|---|---|
| `architecture.md` | Components and data flow |
| `sensor/` | Tetragon/auditd setup, tracing policies, captured events |
| `forwarder/` | Filtering, attribution, redaction, delivery |
| `backend/` | API reference, event schema, validation |
| `detection/` | Rules, correlation, detection record format |
| `splunk/` | HEC setup, indexes, sourcetypes, searches, dashboards |
| `agent/` | Monitored agents, session attribution |
| `deployment/` | Environments, install, CI/CD |
| `evaluation/` | Test harness, scenarios, metrics, results, demo replay |
| `decisions/` | One page per decision: `NNN-short-title.md` |

A folder's landing page is `index.md`. Update an existing page before adding a new one.

## How to write
Concise. Too sparse beats too long.
- Lead with the fact. No intros, overviews that restate the title, summaries, or closing paragraphs.
- No mannered or padded prose ("This section describes...", "It is important to note...", "In order to..."). Plain present tense.
- Tables for fields, endpoints, config, and options. Code blocks for every command and payload.
- Each fact lives on one page; link to it elsewhere instead of repeating it.
- Mermaid diagrams only when a flow is hard to follow in text.
- No AI attribution.

Decision pages use exactly:
```markdown
# NNN: <decision>

**Decision:** <one sentence>
**Why:** <1-3 sentences>
**Rejected:** <option>: <reason>; <option>: <reason>
```

## Check
```bash
pip install -r docs/requirements.txt
mkdocs build --strict   # must pass; CI runs the same
mkdocs serve            # preview at http://127.0.0.1:8000
```

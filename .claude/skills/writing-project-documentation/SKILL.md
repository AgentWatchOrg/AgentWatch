---
name: writing-project-documentation
description: Use whenever a change in AgentWatch adds or changes something non-trivial (component, API, schema, configuration, deployment step, detection rule, Splunk setup, spike decision), and whenever writing or editing anything under documentation/. Keeps the GitHub Pages documentation current, concise, and free of bloat.
---

# Writing project documentation

Documentation lives in `documentation/` as Markdown and publishes to https://agentwatchorg.github.io/AgentWatch/ on every merge to main.

## When to document
Update documentation in the same PR as the change when it adds or changes:
- a component, API endpoint, or interface between components
- the event schema or detection record format
- configuration, environment variables, or required privileges
- a deployment, setup, or test-run step
- a detection rule or evaluation scenario
- Splunk indexes, sourcetypes, searches, or dashboards
- a decision from a spike (what was chosen and why)

Skip documentation for refactors, renames, typo fixes, and anything a reader would not need to run, integrate with, or understand the system.

## Where
1. Look at the current tree: `ls -R documentation/`.
2. Add to an existing page if the topic is already covered; otherwise add a page to the section it belongs in.
3. Create a new section folder only when the content fits none of the existing ones. Name it for the part of the system it covers.

The navigation builds itself from the folders. A folder's landing page is `index.md`.

## How to write
Concise. Too sparse beats too long.
- Lead with the fact. No intros, overviews that restate the title, summaries, or closing paragraphs.
- No mannered or padded prose ("This section describes...", "It is important to note...", "In order to..."). Plain present tense.
- Tables for fields, endpoints, configuration, and options. Code blocks for every command and payload.
- Each fact lives on one page; link to it elsewhere instead of repeating it.
- Mermaid diagrams only when a flow is hard to follow in text.
- No AI attribution.

When recording a decision (for example a spike's outcome), use exactly:
```markdown
# NNN: <decision>

**Decision:** <one sentence>
**Why:** <1-3 sentences>
**Rejected:** <option>: <reason>; <option>: <reason>
```

## Check
```bash
pip install -r documentation/requirements.txt
mkdocs build --strict   # must pass; CI runs the same
mkdocs serve            # preview at http://127.0.0.1:8000
```

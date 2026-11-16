---
name: writing-pull-request-descriptions
description: Use whenever opening or editing a pull request for AgentWatch. Writes a short title and a minimal Why/What description linked to its ticket.
---

# Writing pull request descriptions

As short as possible. Too sparse is fine; too long is not.

## Size
Over 500 changed lines: stop and split it using the `splitting-large-pull-requests-into-stacks` skill.

## Ticket link (required)
Every PR closes a ticket. Find the number from the branch name, commits, or the conversation. If none exists, create one with the `creating-github-issues` skill first. Never open a PR without `Closes #N`.

## Title
Under ~60 characters, imperative, no ticket number, no prefix: "Add HEC export retry".

## Body
Exactly this, nothing more:

```
Closes #<N>

**Why:** <one sentence>

**What:**
- <change>
- <change>
```

- Why: one sentence. What: 1-3 bullets, a few words each.
- No testing notes, screenshots sections, checklists, file lists, or headings beyond these unless the user asks.
- No filler or mannered prose ("This PR introduces...", "In order to..."). Say it directly.
- No AI attribution or "Generated with" footer.

## Open it
```bash
gh pr create -R AgentWatchOrg/AgentWatch --title "<title>" --body-file - <<'EOF'
<body>
EOF
```

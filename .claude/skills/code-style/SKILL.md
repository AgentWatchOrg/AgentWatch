---
name: code-style
description: Use whenever writing or editing any code in AgentWatch (Python, shell, YAML, anything). Descriptive names instead of comments, full type hints, comments only when absolutely necessary.
---

# Code style

The code explains itself through names and types. Comments are a last resort.

## Names
- Variables, functions, classes, and files get names long enough that no comment is needed: `unfinished_project_items`, not `items`; `move_item_to_week()`, not `update()`.
- No abbreviations except universal ones (`id`, `url`, `api`, `json`).
- Booleans read as questions: `is_finished`, `has_next_page`, `should_post_summary`.
- If a block needs a comment to explain what it does, extract it into a function whose name says it.

## Type hints
- Every function parameter and return value is typed.
- Every variable is annotated where it is first assigned: `retry_count: int = 0`, `events: list[TelemetryEvent] = []`.
- Use precise types (`TypedDict`, dataclasses, `Literal`, aliases) over `Any` and bare `dict`.
- Code must pass `mypy --strict` (Python) or the equivalent checker for the language.

## Comments
Write one only when the code cannot say it: a non-obvious **why**, such as an external API quirk, a workaround, or a constraint from somewhere else. One line, plain words.

Never write:
- Module, class, or function docstrings that narrate what the code does, list steps, or document config. Names and types already say it.
- Comments restating the code (`# loop over items`, `# return the result`).
- Section banners, separators, or headers.
- Change notes (`# added X`, `# fixed Y`, `# new`), TODOs without a ticket number, or commented-out code.
- Mannered or padded prose ("This function is responsible for...", "Note that...", "It is important to...").

When editing existing code, do not add comments to lines you did not need to change.

## Example
Bad:
```python
def proc(d):
    """Process the data and return results.

    Loops over each item and keeps the ones that are not done.
    """
    # keep unfinished
    r = [x for x in d if x["s"] != "Done"]
    return r
```

Good:
```python
def unfinished_items(project_items: list[ProjectItem]) -> list[ProjectItem]:
    unfinished: list[ProjectItem] = [item for item in project_items if item.status != "Done"]
    return unfinished
```

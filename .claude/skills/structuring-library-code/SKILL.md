---
name: structuring-library-code
description: Use whenever writing or changing Python in AgentWatch. Core logic goes in lib/src/agent_watch/api so the CLI and the REST API can call it; both are thin layers; every file is ordered imports, globals, classes, functions; every function has a pytest unit test.
---

# Structuring library code

Everything lives in the `agent-watch` package under `lib/`: core logic in `api`, and two thin layers over it, the Click CLI in `cli` and the FastAPI REST API in `rest_api`.

```
lib/src/agent_watch/
  api/                    core logic, reusable
    github_client.py      shared clients for external services
    <area>/
      models.py           dataclasses, enums, exceptions, constants for the area
      <service>_client.py reads and writes an external service, returns models
      <use_case>.py       one module per operation
  cli/                    Click entry points only
    main.py               the agent-watch group
    <area>_commands.py    one command group per area
  rest_api/               FastAPI entry points only, behind the `rest-api` extra
    application.py        create_application(); includes every router
    routers/<area>_router.py
lib/tests/                mirrors src/agent_watch: tests/api/<area>/test_<module>.py, tests/cli/test_<module>.py,
                          tests/rest_api/routers/test_<area>_router.py
  conftest.py             fixtures shared by every test; nested conftest.py for fixtures used by one folder
  doubles/                fake classes and factory Protocol types: <area>_test_doubles.py
```

## api
Callable from the CLI and the REST API with no changes.
- Takes plain arguments and clients as parameters. Returns models.
- Never prints, reads environment variables, parses arguments, exits, or imports `click`.
- Raises a specific exception from the area's `models.py` on failure.
- Split each operation into a pure `plan_*` function (inputs → planned changes, no I/O), an `apply_*` function (performs the plan through a client), and one function that loads, plans, and applies unless it's a dry run.
- Clients are classes that take their dependencies in `__init__`, so tests can pass fakes.

## cli
- Parses options (each with an `envvar`), builds clients, calls one api function, prints the result.
- No business logic. If a command needs more than formatting, the logic belongs in `api`.

## rest_api
- Add an endpoint only for something a client of AgentWatch needs over HTTP. Don't mirror CLI commands.
- Routes call one api function and return its models; FastAPI serializes dataclasses.
- Build api clients in FastAPI dependencies and read environment variables in one settings module, so tests can override them.
- No business logic in routers; same rule as `cli`.
- Tests use `fastapi.testclient.TestClient` with `dependency_overrides` and `monkeypatch` on the api function.

## File layout
Every file in this order:
1. imports
2. module constants and globals
3. classes: exceptions, enums, dataclasses, then other classes
4. functions

## Tests
- Every function and method gets a pytest test in the test module at the matching path (`src/agent_watch/api/x/y.py` → `tests/api/x/test_y.py`), in the same PR.
- Test `plan_*` functions directly with model objects.
- Test clients with a fake of the client they depend on; never call the real GitHub API.
- Test commands with `click.testing.CliRunner` and `monkeypatch` on the api function.
- Get test data and fakes from pytest fixtures, never by constructing them inline in each test. Put a fixture in the nearest `conftest.py` that covers every test using it, or in the test module if only it uses the fixture.
- Fixtures that need arguments return a factory; type it with a `Protocol` from `lib/tests/doubles/<area>_test_doubles.py`, where fake classes also live.
- Use `@pytest.mark.parametrize` (with `ids`) when tests differ only in inputs and expected output.
- Plain `assert` and `pytest.raises`; no unittest-style assertions.
- Tests follow the same naming, typing, and layout rules as source.

```bash
cd lib && mypy src tests && pytest
```
Both must pass; `run_type_checks_and_unit_tests` is a required check on main.

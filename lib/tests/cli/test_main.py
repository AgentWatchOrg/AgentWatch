from click.testing import CliRunner, Result

from agent_watch.cli.main import agent_watch


def test_version_option_prints_the_package_version() -> None:
    result: Result = CliRunner().invoke(agent_watch, ["--version"])

    assert result.exit_code == 0
    assert result.output.startswith("agent-watch, version ")

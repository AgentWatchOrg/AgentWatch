import click

from agent_watch.cli.project_board_commands import project_board
from agent_watch.cli.pull_request_review_commands import pull_request_review
from agent_watch.utilities.logging_configuration import (
    DEFAULT_LOG_LEVEL_NAME, LOG_LEVEL_ENVIRONMENT_VARIABLE, LOG_LEVEL_NAMES, configure_logging)


@click.group(help="AgentWatch command line interface.")
@click.option("--log-level", envvar=LOG_LEVEL_ENVIRONMENT_VARIABLE, default=DEFAULT_LOG_LEVEL_NAME, show_default=True,
              type=click.Choice(LOG_LEVEL_NAMES, case_sensitive=False), help=f"Env: {LOG_LEVEL_ENVIRONMENT_VARIABLE}")
def agent_watch(log_level: str) -> None:
    configure_logging(log_level)


agent_watch.add_command(project_board)
agent_watch.add_command(pull_request_review)

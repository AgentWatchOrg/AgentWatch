import click

from agent_watch.cli.project_board_commands import project_board
from agent_watch.cli.pull_request_review_commands import pull_request_review


@click.group(help="AgentWatch command line interface.")
def agent_watch() -> None:
    pass


agent_watch.add_command(project_board)
agent_watch.add_command(pull_request_review)

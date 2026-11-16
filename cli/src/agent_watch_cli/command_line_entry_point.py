import click

from agent_watch_cli import __version__
from agent_watch_cli.project_board.project_board_commands import project_board


@click.group(help="Command line tools for the AgentWatch project.")
@click.version_option(__version__, prog_name="agent-watch")
def agent_watch() -> None:
    pass


agent_watch.add_command(project_board)

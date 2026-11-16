import click

from agent_watch.cli.project_board_commands import project_board


@click.group(help="AgentWatch command line interface.")
@click.version_option(package_name="agent-watch", prog_name="agent-watch")
def agent_watch() -> None:
    pass


agent_watch.add_command(project_board)

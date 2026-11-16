import logging
from typing import TextIO

PACKAGE_LOGGER_NAME: str = "agent_watch"
LOG_FORMAT: str = "%(levelname)s %(name)s: %(message)s"
LOG_LEVEL_NAMES: list[str] = ["DEBUG", "INFO", "WARNING", "ERROR"]
LOG_LEVEL_ENVIRONMENT_VARIABLE: str = "AGENT_WATCH_LOG_LEVEL"
DEFAULT_LOG_LEVEL_NAME: str = "INFO"


def configure_logging(level_name: str) -> None:
    package_logger: logging.Logger = logging.getLogger(PACKAGE_LOGGER_NAME)
    for existing_handler in list(package_logger.handlers):
        package_logger.removeHandler(existing_handler)
    stream_handler: logging.StreamHandler[TextIO] = logging.StreamHandler()
    stream_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    package_logger.addHandler(stream_handler)
    package_logger.setLevel(level_name.upper())
    package_logger.propagate = False

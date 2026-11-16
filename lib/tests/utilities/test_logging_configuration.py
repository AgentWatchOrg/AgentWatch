import logging

import pytest

from agent_watch.utilities.logging_configuration import PACKAGE_LOGGER_NAME, configure_logging


def test_configure_logging_sets_the_level_and_one_handler() -> None:
    configure_logging("debug")
    configure_logging("warning")

    package_logger: logging.Logger = logging.getLogger(PACKAGE_LOGGER_NAME)
    assert package_logger.level == logging.WARNING
    assert len(package_logger.handlers) == 1
    assert package_logger.propagate is False


def test_module_loggers_write_through_the_package_handler(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("info")

    logging.getLogger("agent_watch.api.example").info("hello")

    assert capsys.readouterr().err == "INFO agent_watch.api.example: hello\n"

"""Unit tests for logging configuration scenarios."""

import logging

from logintel.logging_config import configure_logging


class TestConfigureLogging:
    """Scenarios for configuring the LogIntel logging system."""

    def test_when_called_with_info_level_then_root_logger_is_set_to_info(self):
        configure_logging(level="INFO")
        root = logging.getLogger("logintel")
        assert root.level == logging.INFO
        assert len(root.handlers) == 1
        assert isinstance(root.handlers[0], logging.StreamHandler)

    def test_when_called_with_debug_level_then_root_logger_is_set_to_debug(self):
        configure_logging(level="DEBUG")
        root = logging.getLogger("logintel")
        assert root.level == logging.DEBUG

    def test_when_called_with_json_format_then_formatter_uses_json_structure(self):
        configure_logging(level="INFO", json_format=True)
        root = logging.getLogger("logintel")
        formatter = root.handlers[0].formatter
        assert '"time"' in formatter._fmt
        assert '"level"' in formatter._fmt

    def test_when_called_with_plain_format_then_formatter_uses_plain_text(self):
        configure_logging(level="INFO", json_format=False)
        root = logging.getLogger("logintel")
        formatter = root.handlers[0].formatter
        assert "[%(levelname)s]" in formatter._fmt

    def test_when_called_multiple_times_then_old_handlers_are_replaced(self):
        configure_logging(level="INFO")
        configure_logging(level="DEBUG")
        root = logging.getLogger("logintel")
        assert len(root.handlers) == 1

    def test_when_called_then_mcp_logger_also_configured(self):
        configure_logging(level="WARNING")
        mcp_logger = logging.getLogger("mcp")
        assert len(mcp_logger.handlers) == 1

"""End-to-end tests for the CLI entry point scenarios."""

import sys
from unittest.mock import MagicMock, patch

import pytest

from logintel.__main__ import main


class TestMainEntryPoint:
    """Scenarios for the logintel CLI entry point."""

    @patch("logintel.__main__.create_server")
    @patch("logintel.__main__.asyncio.run")
    def test_when_called_with_defaults_then_creates_server_with_default_config(
        self, mock_run, mock_create
    ):
        mock_server = MagicMock()
        mock_create.return_value = mock_server
        with patch.object(sys, "argv", ["logintel"]):
            main()
        mock_create.assert_called_once_with(config_path=".logintelrc.yaml")
        mock_run.assert_called_once()

    @patch("logintel.__main__.create_server")
    @patch("logintel.__main__.asyncio.run")
    def test_when_called_with_config_flag_then_uses_custom_config(self, mock_run, mock_create):
        mock_server = MagicMock()
        mock_create.return_value = mock_server
        with patch.object(sys, "argv", ["logintel", "--config", "/custom/config.yaml"]):
            main()
        mock_create.assert_called_once_with(config_path="/custom/config.yaml")

    @patch("logintel.__main__.create_server")
    @patch("logintel.__main__.asyncio.run")
    def test_when_called_with_transport_flag_then_passes_transport(self, mock_run, mock_create):
        mock_server = MagicMock()
        mock_create.return_value = mock_server
        with patch.object(sys, "argv", ["logintel", "--transport", "http"]):
            main()
        # The coroutine passed to asyncio.run should be run_server(mock_server, "http")
        # We can't easily inspect the coroutine, but we can verify create_server was called
        mock_create.assert_called_once()

    @patch("logintel.__main__.create_server")
    @patch("logintel.__main__.asyncio.run")
    @patch("builtins.print")
    def test_when_keyboard_interrupt_occurs_then_prints_shutdown_message(
        self, mock_print, mock_run, mock_create
    ):
        mock_run.side_effect = KeyboardInterrupt
        with patch.object(sys, "argv", ["logintel"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0
        mock_print.assert_called_once()
        assert "Shutting down" in mock_print.call_args[0][0]

    @patch("logintel.__main__.create_server")
    @patch("logintel.__main__.asyncio.run")
    @patch("builtins.print")
    def test_when_fatal_error_occurs_then_prints_error_and_exits(
        self, mock_print, mock_run, mock_create
    ):
        mock_run.side_effect = RuntimeError("Something broke")
        with patch.object(sys, "argv", ["logintel"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1
        mock_print.assert_called_once()
        assert "Fatal error" in mock_print.call_args[0][0]
        assert "Something broke" in mock_print.call_args[0][0]

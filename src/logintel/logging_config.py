"""Logging configuration — stderr only, structured JSON optional."""

import logging
import sys


def configure_logging(level: str = "INFO", json_format: bool = False) -> None:
    """Configure root logger to output to stderr only."""
    handler = logging.StreamHandler(sys.stderr)

    if json_format:
        fmt = (
            '{"time": "%(asctime)s", "level": "%(levelname)s", '
            '"name": "%(name)s", "message": "%(message)s"}'
        )
    else:
        fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

    handler.setFormatter(logging.Formatter(fmt))

    root = logging.getLogger("logintel")
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.handlers = []
    root.addHandler(handler)

    # Also configure mcp SDK logs to stderr
    mcp_logger = logging.getLogger("mcp")
    mcp_logger.handlers = []
    mcp_logger.addHandler(handler)

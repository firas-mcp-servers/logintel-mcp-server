"""Entry point for the LogIntel MCP server."""

import argparse
import asyncio
import sys

from logintel.server import create_server, run_server


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="LogIntel MCP Server")
    parser.add_argument(
        "--config",
        "-c",
        type=str,
        default=".logintelrc.yaml",
        help="Path to configuration file (default: .logintelrc.yaml)",
    )
    parser.add_argument(
        "--transport",
        "-t",
        type=str,
        default="stdio",
        choices=["stdio", "http"],
        help="Transport protocol (default: stdio)",
    )
    args = parser.parse_args()

    try:
        server = create_server(config_path=args.config)
        asyncio.run(run_server(server, transport=args.transport))
    except KeyboardInterrupt:
        print("\nShutting down LogIntel MCP server...", file=sys.stderr)
        sys.exit(0)
    except Exception as exc:  # noqa: BLE001
        print(f"Fatal error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

#!/usr/bin/env node
/**
 * LogIntel MCP Server — npm wrapper for the Python package.
 *
 * This wrapper assumes the Python package `logintel-mcp` is installed
 * (either globally, in a virtualenv, or via the postinstall script).
 *
 * Usage:
 *   npx -y @logintel/mcp-server --config /path/to/.logintelrc.yaml
 */

const { spawn } = require("child_process");
const path = require("path");

function findPython() {
  return process.env.LOGINTEL_PYTHON || "python3";
}

function main() {
  const python = findPython();
  const args = ["-m", "logintel", ...process.argv.slice(2)];

  const child = spawn(python, args, {
    stdio: "inherit",
    shell: false,
  });

  child.on("exit", (code) => {
    process.exitCode = code ?? 0;
  });

  child.on("error", (err) => {
    if (err.code === "ENOENT") {
      console.error(
        "Error: Could not find Python interpreter.",
        "Please install Python 3.11+ and ensure 'python3' is in your PATH,",
        "or set the LOGINTEL_PYTHON environment variable."
      );
    } else {
      console.error("Error spawning LogIntel:", err.message);
    }
    process.exit(1);
  });
}

main();

/**
 * Post-install script: attempt to install the Python package via pip/uv.
 */

const { execSync } = require("child_process");

function run(cmd) {
  try {
    execSync(cmd, { stdio: "inherit" });
    return true;
  } catch {
    return false;
  }
}

function main() {
  console.log("Checking for logintel-mcp Python package...");

  // Check if already installed
  try {
    execSync("python3 -c 'import logintel'", { stdio: "ignore" });
    console.log("logintel-mcp is already installed.");
    return;
  } catch {
    // not installed, try to install
  }

  console.log("Attempting to install logintel-mcp via uv...");
  if (run("uv pip install logintel-mcp")) return;

  console.log("Attempting to install logintel-mcp via pip...");
  if (run("python3 -m pip install logintel-mcp")) return;

  console.log(
    "Warning: Could not auto-install logintel-mcp.",
    "Please install manually: pip install logintel-mcp"
  );
}

main();

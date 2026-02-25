#!/usr/bin/env bash
set -euo pipefail

VAULT="${1:?Usage: ./test-inspector.sh <vault-name> [config]}"
CONFIG="${2:-obsidian}"
LOG="inspector.log"

echo "Installing climax-mcp from git..."
uv tool install "climax-mcp @ git+https://github.com/get2knowio/climax.git" 2>&1 | tee "$LOG"

echo "Starting MCP Inspector (logging to $LOG)..."
echo "Open the URL printed above in your browser. Press Ctrl-C when done."
OBSIDIAN_VAULT="$VAULT" npx @modelcontextprotocol/inspector climax -- "$CONFIG" >> "$LOG" 2>&1 || true

echo "Cleaning up..."
uv tool uninstall climax-mcp 2>&1 | tee -a "$LOG"
echo "Done. Log saved to $LOG"

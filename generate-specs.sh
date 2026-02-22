#!/bin/bash
# generate-specs.sh — Run speckit.specify across all spec prompts in the vault
#
# Reads markdown files from the vault's spec-prompts directory,
# extracts the prompt from ```speckit fenced blocks, and passes
# each to Claude Code via /speckit.specify in YOLO mode.
#
# Each spec gets its own branch (created by speckit).
# Returns to main between specs so branches don't stack.

set -euo pipefail

VAULT_SPEC_DIR="$HOME/Library/Mobile Documents/iCloud~md~obsidian/Documents/get2know/projects/climax/spec-prompts"
PROJECT_DIR="$HOME/GitHub/climax"

cd "$PROJECT_DIR"

# Ensure we start clean on main
git checkout main 2>/dev/null || true

# Find all spec prompt files in order
SPEC_FILES=$(find "$VAULT_SPEC_DIR" -name '*.md' | sort)

if [ -z "$SPEC_FILES" ]; then
  echo "❌ No spec prompt files found in $VAULT_SPEC_DIR"
  exit 1
fi

echo "🔍 Found spec prompt files:"
echo "$SPEC_FILES" | while read -r f; do echo "   $(basename "$f")"; done
echo ""

for SPEC_FILE in $SPEC_FILES; do
  BASENAME=$(basename "$SPEC_FILE")
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "📋 Processing: $BASENAME"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

  # Extract prompt from ```speckit ... ``` fenced block
  PROMPT=$(sed -n '/^```speckit$/,/^```$/{ /^```/d; p; }' "$SPEC_FILE")

  if [ -z "$PROMPT" ]; then
    echo "⚠️  No \`\`\`speckit block found in $BASENAME — skipping"
    echo ""
    continue
  fi

  echo "📤 Sending to Claude Code..."
  echo ""

  # Return to main before each spec so branches don't nest
  git checkout main 2>/dev/null || true

  # Fire it off in YOLO mode
  claude -p --dangerously-skip-permissions "/speckit.specify $PROMPT"

  BRANCH=$(git branch --show-current)
  echo ""
  echo "✅ Done: $BASENAME → branch: $BRANCH"
  echo ""
done

# Return to main when finished
git checkout main 2>/dev/null || true

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🏁 All specs processed. Branches created:"
git branch | grep -v '^\* main$' | grep -v '^  main$' || echo "   (none — check for errors above)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

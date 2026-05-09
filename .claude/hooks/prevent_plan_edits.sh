#!/bin/bash

# Claude Code exports the current mode to the environment
if [[ "$CLAUDE_PERMISSION_MODE" == "plan" ]]; then
  # Outputting a JSON decision allows you to provide a specific reason to Claude
  echo '{"decision": "block", "reason": "CRITICAL: You are currently in Plan Mode. File edits are strictly forbidden. Please finish the plan and switch to a different mode before attempting to modify files."}'
  exit 0
fi

# If not in plan mode, allow the tool to proceed
exit 0
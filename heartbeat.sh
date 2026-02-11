#!/bin/bash
# Dashboard heartbeat — runs as a Claude Code Stop hook.
#
# Throttled: only calls Python if last heartbeat was > 15 min ago.
# Typical execution time when skipped: <5ms (two stat calls).
# Typical execution time when updating: ~150ms (Python startup + JSON write).

set -euo pipefail

DASHBOARD_DIR="$HOME/.claude/dashboard"
THROTTLE_DIR="$DASHBOARD_DIR/.throttle"
INTERVAL=900  # 15 minutes in seconds

# Derive project slug from CLAUDE_PROJECT_DIR (set by Claude Code)
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$PWD}"
SLUG=$(basename "$PROJECT_DIR" | tr '[:upper:]' '[:lower:]' | tr '_' '-')

# Throttle file per project
mkdir -p "$THROTTLE_DIR"
THROTTLE_FILE="$THROTTLE_DIR/$SLUG"

# Fast path: if throttle file is recent, skip
if [ -f "$THROTTLE_FILE" ]; then
    if [ "$(uname)" = "Darwin" ]; then
        LAST_MOD=$(stat -f %m "$THROTTLE_FILE" 2>/dev/null || echo 0)
    else
        LAST_MOD=$(stat -c %Y "$THROTTLE_FILE" 2>/dev/null || echo 0)
    fi
    NOW=$(date +%s)
    DIFF=$(( NOW - LAST_MOD ))
    [ "$DIFF" -lt "$INTERVAL" ] && exit 0
fi

# Update heartbeat for all active sessions of this project
python3 "$DASHBOARD_DIR/manage.py" heartbeat-project "$SLUG" > /dev/null 2>&1 || true

# Touch throttle file for next check
touch "$THROTTLE_FILE"

exit 0

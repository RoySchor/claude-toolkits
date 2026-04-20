#!/bin/bash
# state_tracker.sh — Claude Code hook that writes per-session state files
# Registered for: SessionStart, UserPromptSubmit, Stop, SessionEnd
# Receives session JSON on stdin

STATE_DIR="$HOME/.claude-toolkits/state"
mkdir -p "$STATE_DIR"

INPUT=$(cat)
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty')
EVENT=$(echo "$INPUT" | jq -r '.hook_event_name // empty')
CWD=$(echo "$INPUT" | jq -r '.cwd // empty')
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

if [ -z "$SESSION_ID" ] || [ -z "$EVENT" ]; then
    exit 0
fi

case "$EVENT" in
    "SessionStart")
        STATE="idle"
        ;;
    "UserPromptSubmit")
        STATE="cooking"
        ;;
    "Stop")
        STATE="idle"
        ;;
    "SessionEnd")
        rm -f "$STATE_DIR/$SESSION_ID.json"
        exit 0
        ;;
    *)
        exit 0
        ;;
esac

jq -n \
    --arg session_id "$SESSION_ID" \
    --arg state "$STATE" \
    --arg timestamp "$TIMESTAMP" \
    --arg cwd "$CWD" \
    --arg event "$EVENT" \
    '{session_id: $session_id, state: $state, timestamp: $timestamp, cwd: $cwd, last_event: $event}' \
    > "$STATE_DIR/$SESSION_ID.json"

exit 0

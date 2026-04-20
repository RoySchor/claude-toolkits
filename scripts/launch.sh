#!/bin/bash
# Tmux sidebar launcher for ct dash
# Creates a split: 30% left (dashboard TUI) | 70% right (user shell)
# Re-running reattaches to existing session. F12 toggles sidebar visibility.

SESSION_NAME="claude-dash"
DASH_CMD="ct dash --fullscreen"

# If explicitly told fullscreen, just run the TUI
if [ "$1" = "--fullscreen" ]; then
    exec $DASH_CMD
fi

# If already inside this tmux session, run TUI directly (avoid recursion)
if [ -n "$TMUX" ]; then
    CURRENT_SESSION=$(tmux display-message -p '#S' 2>/dev/null)
    if [ "$CURRENT_SESSION" = "$SESSION_NAME" ]; then
        exec $DASH_CMD
    fi
fi

# If session already exists, attach to it
if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    exec tmux attach-session -t "$SESSION_NAME"
fi

# Create new session with split layout
COLS=$(tput cols 2>/dev/null || echo 120)
LINES=$(tput lines 2>/dev/null || echo 40)

tmux new-session -d -s "$SESSION_NAME" -x "$COLS" -y "$LINES"

# Split: left pane (30%) for dashboard, right pane (70%) for shell
tmux split-window -h -t "$SESSION_NAME" -l 70%

# Run dashboard in the left pane (pane 0)
tmux send-keys -t "${SESSION_NAME}:0.0" "$DASH_CMD" Enter

# Bind F12 to toggle dashboard pane
tmux bind-key -n F12 if-shell \
    "tmux list-panes -t ${SESSION_NAME} | wc -l | grep -q 2" \
    "break-pane -d -t ${SESSION_NAME}:0.0" \
    "join-pane -b -h -l 30% -t ${SESSION_NAME} -s ${SESSION_NAME}:1"

# Focus the right pane (shell) and attach
tmux select-pane -t "${SESSION_NAME}:0.1"
exec tmux attach-session -t "$SESSION_NAME"

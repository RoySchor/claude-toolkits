#!/bin/bash
# Tmux sidebar launcher for ct dash
# Creates a split: 30% left (dashboard TUI) | 70% right (user shell)
# Re-running reattaches to existing session. F12 toggles sidebar visibility.

SESSION_NAME="claude-dash"
DASH_CMD=(ct dash --fullscreen)

# If explicitly told fullscreen, just run the TUI
if [ "$1" = "--fullscreen" ]; then
    exec "${DASH_CMD[@]}"
fi

# If already inside this tmux session, run TUI directly (avoid recursion)
if [ -n "$TMUX" ]; then
    CURRENT_SESSION=$(tmux display-message -p '#S' 2>/dev/null)
    if [ "$CURRENT_SESSION" = "$SESSION_NAME" ]; then
        exec "${DASH_CMD[@]}"
    fi
fi

# If session already exists, attach to it
if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    exec tmux attach-session -t "$SESSION_NAME"
fi

# Create new session with split layout
WIN_COLS=$(tput cols 2>/dev/null || echo 120)
WIN_ROWS=$(tput lines 2>/dev/null || echo 40)

tmux new-session -d -s "$SESSION_NAME" -x "$WIN_COLS" -y "$WIN_ROWS"

# Split: left pane (20%) for dashboard, right pane (70%) for shell
tmux split-window -h -t "$SESSION_NAME" -l 80%

# Run dashboard in the left pane (pane 0)
tmux send-keys -t "${SESSION_NAME}:0.0" "ct dash --fullscreen" Enter

# Capture the dashboard pane ID for reliable F12 toggle
DASH_PANE_ID=$(tmux display-message -t "${SESSION_NAME}:0.0" -p '#{pane_id}')
tmux set-environment -t "$SESSION_NAME" DASH_PANE_ID "$DASH_PANE_ID"

# Bind F12 to toggle dashboard pane visibility using tracked pane ID
tmux bind-key -n F12 run-shell '
    PANE=$(tmux show-environment -t claude-dash DASH_PANE_ID 2>/dev/null | cut -d= -f2)
    if [ -z "$PANE" ]; then exit 0; fi
    if tmux list-panes -F "#{pane_id}" 2>/dev/null | grep -q "^${PANE}$"; then
        tmux break-pane -d -t "$PANE"
    else
        tmux join-pane -b -h -l 20% -t claude-dash:0 -s "$PANE"
    fi
'

# Bind F11 to toggle focus between dashboard and shell panes
tmux bind-key -n F11 select-pane -t "{next}"

# Focus the right pane (shell) and attach
tmux select-pane -t "${SESSION_NAME}:0.1"
exec tmux attach-session -t "$SESSION_NAME"

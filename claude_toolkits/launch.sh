#!/bin/bash
# Tmux sidebar launcher for ct dash
# Ctrl+B h = switch pane focus, Ctrl+B Space = toggle sidebar

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

# If session already exists, reattach only if dashboard pane is still alive
if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    DASH_PANE=$(tmux show-environment -t "$SESSION_NAME" DASH_PANE_ID 2>/dev/null | cut -d= -f2)
    if [ -n "$DASH_PANE" ] && tmux list-panes -a -F '#{pane_id}' 2>/dev/null | grep -q "^${DASH_PANE}$"; then
        exec tmux attach-session -t "$SESSION_NAME"
    else
        tmux kill-session -t "$SESSION_NAME"
    fi
fi

# Create new session with split layout
WIN_COLS=$(tput cols 2>/dev/null || echo 120)
WIN_ROWS=$(tput lines 2>/dev/null || echo 40)

tmux new-session -d -s "$SESSION_NAME" -x "$WIN_COLS" -y "$WIN_ROWS"

# Shell pane gets most of the width; dashboard gets the rest
SHELL_COLS=$((WIN_COLS * 99 / 100))
tmux split-window -h -t "$SESSION_NAME" -l "$SHELL_COLS"

# Run dashboard in the left pane (pane 0)
tmux send-keys -t "${SESSION_NAME}:0.0" "ct dash --fullscreen" Enter

# Capture the dashboard pane ID for reliable toggle
DASH_PANE_ID=$(tmux display-message -t "${SESSION_NAME}:0.0" -p '#{pane_id}')
tmux set-environment -t "$SESSION_NAME" DASH_PANE_ID "$DASH_PANE_ID"

# Ctrl+B Space = toggle dashboard visibility using tracked pane ID
tmux bind-key Space run-shell '
    PANE=$(tmux show-environment -t claude-dash DASH_PANE_ID 2>/dev/null | cut -d= -f2)
    if [ -z "$PANE" ]; then exit 0; fi
    if tmux list-panes -F "#{pane_id}" 2>/dev/null | grep -q "^${PANE}$"; then
        tmux break-pane -d -t "$PANE"
    else
        COLS=$(tmux display-message -p "#{window_width}" 2>/dev/null || echo 120)
        DCOLS=$((COLS / 100))
        if [ "$DCOLS" -lt 2 ]; then DCOLS=2; fi
        tmux join-pane -b -h -l "$DCOLS" -t claude-dash:0 -s "$PANE"
    fi
'

# Let tmux notify panes about focus changes so Textual properly
# disables mouse capture when the dashboard pane loses focus
tmux set-option -t "$SESSION_NAME" focus-events on

# Ctrl+B h = switch focus between panes
tmux bind-key h select-pane -t "{next}"

# Focus the right pane (shell) and attach
tmux select-pane -t "${SESSION_NAME}:0.1"
exec tmux attach-session -t "$SESSION_NAME"

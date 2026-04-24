# claude-toolkits

Terminal dashboard for monitoring concurrent Claude Code sessions.

![Dashboard](https://img.shields.io/badge/TUI-Textual-blue) ![Platform](https://img.shields.io/badge/platform-macOS-lightgrey)

## Quick Start

```bash
pip install -e .
brew install tmux jq
ct setup
source ~/.zshrc      # or open a new terminal tab
```

Close any existing Claude sessions and reopen them so they start under the wrapper.

```bash
ct dash
```

## What It Does

The dashboard runs as a tmux sidebar alongside your terminal. It shows all your Claude sessions grouped by state, lets you switch between them instantly, and supports trackpad scrollback.

Each Claude session runs inside an invisible tmux layer (`ct-sessions`). The dashboard swaps the right pane between sessions when you press Enter — no tab switching needed.

## Session States

| State | Meaning |
|---|---|
| COOKING | Claude is actively generating |
| NEEDS YOU | Waiting for tool approval |
| RECENT | Turn complete, active within 12h |
| SHELL | Plain terminal session (created from dashboard) |
| STALE | Idle > 12h |
| DEAD | Process exited |

## Dashboard Keys

| Key | Action |
|---|---|
| `Enter` | Switch to selected session |
| `n` | Open a new shell session |
| `d` | Show session detail |
| `r` | Refresh |
| `q` | Quit |
| Arrows | Navigate sessions |
| Trackpad scroll | Scrollback in active session |
| `Ctrl+B h` | Switch focus between dashboard and terminal |
| `Ctrl+B Space` | Toggle dashboard sidebar visibility |
| `Cmd+Opt+drag` | Copy text (bypasses tmux mouse capture) |

## Commands

| Command | Description |
|---|---|
| `ct setup` | One-time setup (hooks + shell wrapper) |
| `ct dash` | Launch dashboard |
| `ct dash --fullscreen` | Dashboard without tmux sidebar |
| `ct status` | Print session table to stdout |
| `ct install-hooks` | Register hooks in `~/.claude/settings.json` |
| `ct install-wrapper` | Add `claude()` wrapper to `~/.zshrc` |
| `ct uninstall-wrapper` | Remove wrapper from `~/.zshrc` |

## How It Works

**Hooks** fire on Claude lifecycle events (`SessionStart`, `Stop`, `PermissionRequest`, etc.) and write state files to `~/.claude-toolkits/state/`. The dashboard polls these files.

**Shell wrapper** (`claude()` in `.zshrc`) starts each Claude session inside a tmux session on the `ct-sessions` socket. The dashboard switches between these sessions in-place.

**Fallback** — sessions started without the wrapper fall back to iTerm2 tab activation. Sessions started before hooks were installed derive state from transcript files.

## Killing the Dashboard

```bash
tmux kill-session -t claude-dash
```

## Requirements

- Python 3.11+
- Claude Code >= 2.1.114
- tmux (`brew install tmux`)
- jq (`brew install jq`)

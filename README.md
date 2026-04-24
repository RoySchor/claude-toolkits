# claude-toolkits

Terminal dashboard for monitoring concurrent Claude Code sessions.

## Quick Start

```bash
pip install -e .    # or pip3 install -e .
brew install tmux   # required for sidebar mode
ct setup            # installs hooks, shell wrapper, reloads shell
```

Then close any existing Claude sessions and reopen them (so they start under the wrapper).

```bash
ct dash             # launch the live dashboard
```

## What `ct setup` Does

1. **Installs hooks** — registers state-tracking hooks in `~/.claude/settings.json` so the dashboard knows session state in real-time
2. **Installs shell wrapper** — adds a `claude()` function to `~/.zshrc` that wraps each session in an invisible tmux layer, enabling in-place session switching from the dashboard
3. **Reloads shell** — sources `~/.zshrc` so the wrapper takes effect immediately

You can also run these individually: `ct install-hooks`, `ct install-wrapper`, `ct uninstall-wrapper`.

## How It Works

**Hook-based detection:** Hooks fire on Claude Code lifecycle events (`SessionStart`, `UserPromptSubmit`, `PermissionRequest`, `PreToolUse`, `SubagentStart`, `Stop`, `SessionEnd`) and write per-session state files to `~/.claude-toolkits/state/`.

**In-place switching:** The shell wrapper starts each Claude session inside a separate tmux server (`ct-sessions`). When you press Enter on a session in the dashboard, it swaps the right pane to that session instantly — no tab switching.

**Fallback:** Sessions started without the wrapper fall back to iTerm2 tab activation via AppleScript. Sessions started before hooks were installed derive state from transcript files.

## Session States

| State | Meaning |
|---|---|
| 🔥 COOKING | Claude is actively generating |
| 🔔 NEEDS YOU | Waiting for tool approval (permission prompt) |
| ✅ RECENT | Turn complete, active < 12h |
| 💤 STALE | Idle > 12h |

## Commands

| Command | Description |
|---|---|
| `ct setup` | One-time setup: hooks + wrapper + shell reload |
| `ct dash` | Launch live TUI dashboard |
| `ct dash --fullscreen` | Dashboard without tmux sidebar |
| `ct status` | Print session table to stdout |
| `ct install-hooks` | Register hooks in Claude settings (idempotent) |
| `ct install-wrapper` | Add `claude()` wrapper to `~/.zshrc` |
| `ct uninstall-wrapper` | Remove wrapper from `~/.zshrc` |

## Dashboard Keybindings

| Key | Action |
|---|---|
| `j`/`k` or arrows | Navigate sessions |
| `Enter` | Open session in right pane (or iTerm2 tab) |
| `d` | Show session detail |
| `r` | Refresh |
| `q` | Quit dashboard |
| `Ctrl+B h` | Switch focus between dashboard and terminal |

## Killing the Dashboard

```bash
tmux kill-session -t claude-dash
```

## Requirements

- Python 3.11+
- Claude Code >= 2.1.114
- tmux (`brew install tmux`)
- `jq` (for hook script)

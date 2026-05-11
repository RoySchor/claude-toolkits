# Claude Toolkits (claude-dash)

Terminal UI dashboard for monitoring concurrent Claude Code sessions, designed to run as a tmux sidebar.

## Language & Stack

- Python 3.11+
- TUI: Textual 3.0+

## Project Structure

```
claude_toolkits/
├── cli.py                  # Entry point — dispatches ct subcommands
├── launch.sh               # Tmux sidebar launcher (splits panes, keybinds)
├── hooks/
│   └── state_tracker.sh    # Bash hook for Claude lifecycle events → writes state JSON
└── dashboard/
    ├── models.py           # Session dataclass, SessionState enum
    ├── scanner.py          # Session discovery — merges 4 data sources into list[Session]
    ├── cache.py            # Incremental transcript parser (backward-scan, mtime tracking)
    ├── app.py              # Textual app — polling, keybindings, session switching
    └── widgets.py          # UI components — SessionList, SessionBucket, SessionItem, DashFooter
```

## Architecture

**Data flow:** Claude Code events → state_tracker.sh → ~/.claude-toolkits/state/*.json → SessionScanner.scan() → DashboardApp (polls 3–30s) → Textual widgets

**Session state sources (priority order):**
1. Hook state files (real-time, from state_tracker.sh)
2. Transcript analysis (fallback for pre-hook sessions)
3. tmux session discovery (for shell sessions)
4. Claude session files (~/.claude/sessions/*.json)

**Session states:** COOKING → NEEDS_YOU → RECENTLY_ACTIVE → STALE → DEAD (+ SHELL for plain terminals)

## Key Paths at Runtime

| Path | Purpose |
|------|---------|
| `~/.claude/sessions/*.json` | Official Claude session metadata |
| `~/.claude/projects/**/*.jsonl` | Transcript files (indexed by session_id stem) |
| `~/.claude-toolkits/state/*.json` | Hook-written real-time state |
| `~/.claude-toolkits/hooks/state_tracker.sh` | Installed hook script |
| `~/.claude/settings.json` | Where hooks are registered |

## Commands

| Command | Does |
|---------|------|
| `ct setup` | Install hooks + wrapper (one-time) |
| `ct dash` | Launch dashboard (tmux sidebar or fullscreen) |
| `ct status` | Print session table to stdout |
| `ct install-hooks` | Register state_tracker.sh in Claude settings |
| `ct install-wrapper` | Add claude() shell function to ~/.zshrc |
| `ct uninstall-wrapper` | Remove wrapper |

## Conventions

- Sort sessions by: state priority → cwd → label (alphabetical)
- `group_by_directory()` in widgets clusters sessions by cwd within each state bucket
- Dead sessions are purged from display after 30 minutes (sentinel: `float('inf')` in `_dead_since`)
- Hook-only sessions pin to their first-seen cwd to avoid flicker
- Trailing slashes are normalized with `.rstrip("/")` before grouping/comparison
- Adaptive polling: 3s when cooking, 5s normal, 30s all stale, pauses after 2h idle


# claude-toolkits

Terminal dashboard for monitoring concurrent Claude Code sessions.

## Quick Start

```bash
pip install -e .
ct install-hooks    # registers state-tracking hooks in ~/.claude/settings.json
ct status           # show all sessions with states
```

## Killing any Existing Sessions

```bash
tmux kill-session -t claude-dash
```

## How It Works

**Primary detection (real-time):** Hooks fire on Claude Code lifecycle events (`SessionStart`, `UserPromptSubmit`, `Stop`, `SessionEnd`) and write per-session state files to `~/.claude-toolkits/state/`.

**Fallback (pre-hook sessions):** For sessions started before hooks were installed, state is derived from transcript file modification times and JSONL content.

## Session States

| State | Meaning |
|---|---|
| 🔥 COOKING | Claude is actively generating |
| 🔔 NEEDS YOU | Waiting for tool approval |
| ✅ RECENT | Turn complete, active < 12h |
| 💤 STALE | Idle > 12h |

## Commands

- `ct status` — Print session table (like `docker ps`)
- `ct install-hooks` — Register hooks in Claude settings (idempotent)
- `ct dash` — Live TUI dashboard (Phase 2, coming soon)

## Requirements

- Python 3.11+
- Claude Code >= 2.1.114
- `jq` (for hook script)

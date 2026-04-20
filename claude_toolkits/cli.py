from __future__ import annotations

import json
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table

from .dashboard.models import SessionState
from .dashboard.scanner import SessionScanner

HOOKS_DIR = Path(__file__).parent / "hooks"
CLAUDE_SETTINGS = Path.home() / ".claude" / "settings.json"
STATE_TRACKER_INSTALL_PATH = Path.home() / ".claude-toolkits" / "hooks" / "state_tracker.sh"


def cmd_status() -> None:
    console = Console()
    scanner = SessionScanner()
    sessions = scanner.scan()

    if not sessions:
        console.print("[dim]No Claude sessions found.[/dim]")
        return

    state_icons = {
        SessionState.COOKING: "[bold red]🔥 COOKING[/bold red]",
        SessionState.NEEDS_YOU: "[bold yellow]🔔 NEEDS YOU[/bold yellow]",
        SessionState.RECENTLY_ACTIVE: "[green]✅ RECENT[/green]",
        SessionState.STALE: "[dim]💤 STALE[/dim]",
        SessionState.DEAD: "[dim red]💀 DEAD[/dim red]",
    }

    table = Table(title="Claude Sessions", show_lines=False, padding=(0, 1))
    table.add_column("State", width=14)
    table.add_column("Name", min_width=20, max_width=30, no_wrap=True, overflow="ellipsis")
    table.add_column("Source", width=8)
    table.add_column("PID", width=7, justify="right")
    table.add_column("Last Activity", width=18)

    for s in sessions:
        state_str = state_icons.get(s.state, str(s.state.value))
        label = s.label
        if s.is_unnamed and s.state != SessionState.DEAD:
            label = f"[yellow]{label}[/yellow]"

        age_str = ""
        if s.last_activity:
            hours = s.age_hours
            if hours is not None:
                if hours < 1:
                    age_str = f"{int(hours * 60)}m ago"
                elif hours < 24:
                    age_str = f"{hours:.1f}h ago"
                else:
                    age_str = f"{hours / 24:.1f}d ago"

        pid_str = str(s.pid) if s.pid else "-"

        table.add_row(state_str, label, s.source, pid_str, age_str)

    console.print(table)
    console.print(f"\n[dim]{len(sessions)} sessions total[/dim]")


def cmd_install_hooks() -> None:
    console = Console()

    install_dir = STATE_TRACKER_INSTALL_PATH.parent
    install_dir.mkdir(parents=True, exist_ok=True)

    source_script = HOOKS_DIR / "state_tracker.sh"
    if not source_script.exists():
        console.print(f"[red]Error: Hook script not found at {source_script}[/red]")
        sys.exit(1)

    STATE_TRACKER_INSTALL_PATH.write_text(source_script.read_text())
    STATE_TRACKER_INSTALL_PATH.chmod(0o755)

    state_dir = Path.home() / ".claude-toolkits" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)

    settings: dict = {}
    if CLAUDE_SETTINGS.exists():
        try:
            settings = json.loads(CLAUDE_SETTINGS.read_text())
        except json.JSONDecodeError:
            console.print("[yellow]Warning: existing settings.json is malformed, creating fresh[/yellow]")
            settings = {}

    hook_command = str(STATE_TRACKER_INSTALL_PATH)
    hook_entry = [{"hooks": [{"type": "command", "command": hook_command}]}]

    hooks = settings.setdefault("hooks", {})
    for event in ("SessionStart", "UserPromptSubmit", "Stop", "SessionEnd"):
        existing = hooks.get(event, [])
        already_installed = any(
            hook_command in json.dumps(rule)
            for rule in existing
        )
        if not already_installed:
            hooks[event] = existing + hook_entry

    CLAUDE_SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    CLAUDE_SETTINGS.write_text(json.dumps(settings, indent=2) + "\n")

    console.print("[green]✓[/green] Hook script installed to: " + str(STATE_TRACKER_INSTALL_PATH))
    console.print("[green]✓[/green] Hooks registered in: " + str(CLAUDE_SETTINGS))
    console.print("[green]✓[/green] State directory: " + str(state_dir))
    console.print("\n[dim]New Claude sessions will now report state in real-time.[/dim]")


def cmd_dash() -> None:
    from .dashboard.app import DashboardApp

    app = DashboardApp()
    app.run()


def main() -> None:
    args = sys.argv[1:]

    if not args or args[0] == "status":
        cmd_status()
    elif args[0] == "install-hooks":
        cmd_install_hooks()
    elif args[0] == "dash":
        cmd_dash()
    else:
        print(f"Unknown command: {args[0]}")
        print("Usage: ct [status|install-hooks|dash]")
        sys.exit(1)

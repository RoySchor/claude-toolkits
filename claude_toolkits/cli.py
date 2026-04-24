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
        SessionState.SHELL: "[bold cyan]>_ SHELL[/bold cyan]",
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
    for event in ("SessionStart", "UserPromptSubmit", "Stop", "SessionEnd",
                   "PermissionRequest", "PreToolUse", "SubagentStart"):
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


WRAPPER_START = "# >>> ct-wrapper (managed by claude-toolkits — do not edit) >>>"
WRAPPER_END = "# <<< ct-wrapper <<<"
WRAPPER_FUNCTION = r'''claude() {
    local dir_slug
    dir_slug=$(basename "$PWD" | tr -cd 'a-zA-Z0-9_-')
    local sess_name="ct-${dir_slug}-$$"

    tmux -L ct-sessions new-session -d -s "$sess_name" \
        -x "$(tput cols)" -y "$(tput lines)" \
        "$(printf '%q ' command claude "$@")"
    tmux -L ct-sessions set -t "$sess_name" status off
    tmux -L ct-sessions set -t "$sess_name" prefix C-@

    tmux -L ct-sessions attach -t "$sess_name"
}'''

ZSHRC = Path.home() / ".zshrc"


def cmd_install_wrapper() -> None:
    console = Console()

    if ZSHRC.exists():
        content = ZSHRC.read_text()
        if WRAPPER_START in content:
            console.print("[yellow]Wrapper already installed in ~/.zshrc[/yellow]")
            return
        if "claude()" in content or "function claude" in content:
            console.print(
                "[red]Error: An existing claude() function or alias found in ~/.zshrc.\n"
                "Remove it first, then re-run ct install-wrapper.[/red]"
            )
            sys.exit(1)
    else:
        content = ""

    block = f"\n{WRAPPER_START}\n{WRAPPER_FUNCTION}\n{WRAPPER_END}\n"
    ZSHRC.write_text(content + block)

    console.print("[green]✓[/green] Shell wrapper installed in ~/.zshrc")
    console.print("[dim]Open a new terminal tab for the wrapper to take effect.[/dim]")
    console.print("[dim]Run 'ct uninstall-wrapper' to remove it.[/dim]")


def cmd_uninstall_wrapper() -> None:
    console = Console()

    if not ZSHRC.exists():
        console.print("[dim]~/.zshrc not found — nothing to remove.[/dim]")
        return

    content = ZSHRC.read_text()
    if WRAPPER_START not in content:
        console.print("[dim]No ct-wrapper block found in ~/.zshrc — nothing to remove.[/dim]")
        return

    start = content.index(WRAPPER_START)
    end = content.index(WRAPPER_END) + len(WRAPPER_END)
    while end < len(content) and content[end] == "\n":
        end += 1
    while start > 0 and content[start - 1] == "\n":
        start -= 1

    cleaned = content[:start] + content[end:]
    ZSHRC.write_text(cleaned)

    console.print("[green]✓[/green] Shell wrapper removed from ~/.zshrc")
    console.print("[dim]Open a new terminal tab for the change to take effect.[/dim]")


def cmd_dash(fullscreen: bool = False) -> None:
    import os
    import shutil

    has_tmux = bool(shutil.which("tmux"))

    if fullscreen or not has_tmux:
        if not has_tmux:
            Console().print(
                "[dim]Tip: Install tmux for sidebar mode: "
                "[bold]brew install tmux[/bold][/dim]\n"
            )
        from .dashboard.app import DashboardApp
        app = DashboardApp()
        app.run(mouse=False)
        return

    launch_script = Path(__file__).parent / "launch.sh"
    if not launch_script.exists():
        from .dashboard.app import DashboardApp
        app = DashboardApp()
        app.run(mouse=False)
        return

    os.execvp("bash", ["bash", str(launch_script)])


def cmd_setup() -> None:
    console = Console()
    console.print("[bold]Setting up claude-toolkits...[/bold]\n")

    console.print("[dim]1/3 Installing hooks...[/dim]")
    cmd_install_hooks()
    console.print()

    console.print("[dim]2/3 Installing shell wrapper...[/dim]")
    cmd_install_wrapper()
    console.print()

    console.print("\n[bold green]Setup complete.[/bold green]")
    console.print(f"[dim]Run: [bold]source {ZSHRC}[/bold] in your current shell, or open a new terminal tab.[/dim]")
    console.print("[dim]Then close existing Claude sessions and reopen them for the wrapper to take effect.[/dim]")
    console.print("[dim]Run 'ct dash' to start the dashboard.[/dim]")


def main() -> None:
    args = sys.argv[1:]

    if not args or args[0] == "status":
        cmd_status()
    elif args[0] == "setup":
        cmd_setup()
    elif args[0] == "install-hooks":
        cmd_install_hooks()
    elif args[0] == "dash":
        fullscreen = "--fullscreen" in args
        cmd_dash(fullscreen=fullscreen)
    elif args[0] == "install-wrapper":
        cmd_install_wrapper()
    elif args[0] == "uninstall-wrapper":
        cmd_uninstall_wrapper()
    else:
        print(f"Unknown command: {args[0]}")
        print("Usage: ct [setup|status|dash [--fullscreen]|install-hooks|install-wrapper|uninstall-wrapper]")
        sys.exit(1)

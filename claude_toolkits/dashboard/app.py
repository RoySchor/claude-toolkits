from __future__ import annotations

import asyncio
import platform
import re
from datetime import datetime, timezone
from time import monotonic

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.timer import Timer
from textual.widgets import Header, Label, Static

from .models import Session, SessionState
from .scanner import SessionScanner, STATE_DIR
from .widgets import DashFooter, SessionList


class DetailModal(ModalScreen[None]):
    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("enter", "dismiss", "Close"),
    ]

    DEFAULT_CSS = """
    DetailModal {
        align: center middle;
    }
    #detail-box {
        width: 60;
        max-height: 20;
        border: thick $accent;
        background: $surface;
        padding: 1 2;
    }
    """

    def __init__(self, session: Session) -> None:
        self.session = session
        super().__init__()

    def compose(self) -> ComposeResult:
        s = self.session
        lines = []
        lines.append(f"[bold]{s.label}[/bold]")
        lines.append("")
        if s.name:
            lines.append(f"Name: {s.name}")
        lines.append(f"State: {s.state.value}")
        lines.append(f"Source: {s.source}")
        if s.pid:
            lines.append(f"PID: {s.pid}")
        if s.cwd:
            lines.append(f"CWD: {s.cwd}")
        if s.last_activity:
            lines.append(f"Last active: {s.last_activity.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        if s.custom_title:
            lines.append(f"Title: {s.custom_title}")
        if s.away_summary:
            lines.append(f"Summary: {s.away_summary}")

        with Vertical(id="detail-box"):
            yield Label("\n".join(lines))


class DashboardApp(App[None]):
    CSS = """
    Screen {
        layout: vertical;
    }
    #session-list {
        height: 1fr;
    }
    #dash-footer {
        dock: bottom;
        height: 2;
        background: $panel;
        color: $text;
        padding: 0 1;
    }
    SessionBucket {
        height: auto;
    }
    SessionItem {
        height: auto;
    }
    SessionItem:hover {
        background: $accent 20%;
    }
    """

    ENABLE_COMMAND_PALETTE = False

    BINDINGS = [
        Binding("q", "quit", "Quit", show=False),
        Binding("r", "refresh", "Refresh", show=False),
        Binding("enter", "open_session", "Open", show=False),
        Binding("d", "detail", "Detail", show=False),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("down", "cursor_down", "Down", show=False),
        Binding("up", "cursor_up", "Up", show=False),
    ]

    TITLE = "Claude Sessions"

    def __init__(self) -> None:
        self._scanner = SessionScanner()
        self._sessions: list[Session] = []
        self._selected_idx: int = 0
        self._poll_interval: float = 5.0
        self._paused: bool = False
        self._all_stale_since: datetime | None = None
        self._poll_task: Timer | None = None
        self._last_refresh: float = 0.0
        self._ct_client: str | None = None
        self._active_ct_session: str | None = None
        super().__init__()

    def compose(self) -> ComposeResult:
        yield Header()
        yield SessionList(id="session-list")
        yield DashFooter(id="dash-footer")

    def on_mount(self) -> None:
        self._do_scan()

    def _do_scan(self) -> None:
        self._sessions = self._scanner.scan()

        if self._selected_idx >= len(self._sessions):
            self._selected_idx = max(0, len(self._sessions) - 1)

        session_list = self.query_one(SessionList)
        session_list.selected_idx = self._selected_idx
        session_list.sessions = self._sessions

        footer = self.query_one(DashFooter)
        footer.session_count = len(self._sessions)
        footer.poll_interval = self._poll_interval
        footer.paused = self._paused
        footer.dead_count = sum(1 for s in self._sessions if s.state == SessionState.DEAD)

        self._adapt_polling()

    def _adapt_polling(self) -> None:
        if not self._sessions:
            self._set_timer(5.0)
            return

        has_cooking = any(s.state == SessionState.COOKING for s in self._sessions)
        all_stale = all(s.state in (SessionState.STALE, SessionState.DEAD) for s in self._sessions)

        if has_cooking:
            new_interval = 3.0
            self._all_stale_since = None
        elif all_stale:
            new_interval = 30.0
            if self._all_stale_since is None:
                self._all_stale_since = datetime.now(timezone.utc)
            else:
                stale_hours = (datetime.now(timezone.utc) - self._all_stale_since).total_seconds() / 3600
                if stale_hours > 2:
                    self._paused = True
                    self._stop_timer()
                    footer = self.query_one(DashFooter)
                    footer.paused = True
                    self.notify("Polling paused — press r to resume", timeout=0)
                    return
        else:
            new_interval = 5.0
            self._all_stale_since = None

        self._set_timer(new_interval)

    def _set_timer(self, interval: float) -> None:
        if interval == self._poll_interval and self._poll_task is not None:
            return
        self._poll_interval = interval
        self._stop_timer()
        self._poll_task = self.set_interval(interval, self._poll_tick)

    def _stop_timer(self) -> None:
        if self._poll_task is not None:
            self._poll_task.stop()
            self._poll_task = None

    def _poll_tick(self) -> None:
        self._do_scan()

    def action_refresh(self) -> None:
        self._paused = False
        self._all_stale_since = None
        now = monotonic()
        if now - self._last_refresh < 2.0:
            return
        self._last_refresh = now
        self.notify("Refreshing\u2026", timeout=1)
        self._do_scan()

    def action_cursor_down(self) -> None:
        if self._sessions:
            self._selected_idx = min(self._selected_idx + 1, len(self._sessions) - 1)
            self._update_selection()

    def action_cursor_up(self) -> None:
        if self._sessions:
            self._selected_idx = max(self._selected_idx - 1, 0)
            self._update_selection()

    def _update_selection(self) -> None:
        session_list = self.query_one(SessionList)
        session_list.selected_idx = self._selected_idx

    async def action_open_session(self) -> None:
        if not self._sessions or not (0 <= self._selected_idx < len(self._sessions)):
            return
        session = self._sessions[self._selected_idx]

        if session.tmux_session_name:
            await self._switch_ct_session(session.tmux_session_name)
            return

        if not session.pid:
            self.notify("No PID for this session", severity="warning")
            return
        if platform.system() != "Darwin":
            self.notify("Open session requires macOS + iTerm2", severity="warning")
            return
        if not await _activate_iterm_session(session.pid):
            self.notify("Could not find session in iTerm2", severity="warning")

    async def _switch_ct_session(self, tmux_name: str) -> None:
        if self._ct_client:
            proc = await asyncio.create_subprocess_exec(
                "tmux", "-L", "ct-sessions", "switch-client",
                "-c", self._ct_client, "-t", tmux_name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.communicate(), timeout=2)
            if proc.returncode == 0:
                self._active_ct_session = tmux_name
                return
            self._ct_client = None

        if self._active_ct_session:
            self.notify("Lost connection to right pane", severity="warning")
            return

        right_pane = await self._get_right_pane_id()
        if not right_pane:
            self.notify("Could not find right pane", severity="warning")
            return

        cmd = f"TMUX= tmux -L ct-sessions attach -t {tmux_name}"
        proc = await asyncio.create_subprocess_exec(
            "tmux", "send-keys", "-t", right_pane, cmd, "Enter",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(proc.communicate(), timeout=2)
        self._active_ct_session = tmux_name

        await asyncio.sleep(0.5)
        self._ct_client = await self._get_ct_client(right_pane)

    async def _get_right_pane_id(self) -> str | None:
        try:
            proc = await asyncio.create_subprocess_exec(
                "tmux", "show-environment", "-t", "claude-dash", "DASH_PANE_ID",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=2)
            raw = stdout.decode().strip()
            dash_pane = raw.split("=", 1)[1] if "=" in raw else ""
            if not dash_pane:
                return None

            proc = await asyncio.create_subprocess_exec(
                "tmux", "list-panes", "-t", "claude-dash",
                "-F", "#{pane_id}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=2)
            panes = [p for p in stdout.decode().strip().splitlines() if p != dash_pane]
            return panes[0] if panes else None
        except (asyncio.TimeoutError, OSError):
            return None

    async def _get_ct_client(self, right_pane: str) -> str | None:
        try:
            proc = await asyncio.create_subprocess_exec(
                "tmux", "display-message", "-t", right_pane,
                "-p", "#{pane_tty}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=2)
            right_tty = stdout.decode().strip()
            if not right_tty:
                return None

            proc = await asyncio.create_subprocess_exec(
                "tmux", "-L", "ct-sessions", "list-clients",
                "-F", "#{client_name} #{client_tty}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=2)
            if proc.returncode != 0:
                return None
            for line in stdout.decode().strip().splitlines():
                parts = line.rsplit(" ", 1)
                if len(parts) == 2 and parts[1] == right_tty:
                    return parts[0]
            return None
        except (asyncio.TimeoutError, OSError):
            return None

    def action_detail(self) -> None:
        if self._sessions and 0 <= self._selected_idx < len(self._sessions):
            self.push_screen(DetailModal(self._sessions[self._selected_idx]))

    def action_quit(self) -> None:
        import subprocess
        self.exit()
        subprocess.run(["tmux", "kill-session", "-t", "claude-dash"], stderr=subprocess.DEVNULL)


_TTY_PATTERN = re.compile(r"^[a-zA-Z0-9/]+$")


async def _activate_iterm_session(pid: int) -> bool:
    try:
        proc = await asyncio.create_subprocess_exec(
            "ps", "-p", str(pid), "-o", "tty=",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=2)
        tty = stdout.decode().strip()
        if not tty or not _TTY_PATTERN.match(tty):
            return False
        tty_path = f"/dev/{tty}"
    except (asyncio.TimeoutError, OSError):
        return False

    script = f'''
        tell application "iTerm2"
            repeat with w in windows
                repeat with t in tabs of w
                    repeat with s in sessions of t
                        if tty of s is "{tty_path}" then
                            select t
                            tell w to select
                            activate
                            return true
                        end if
                    end repeat
                end repeat
            end repeat
            return false
        end tell
    '''
    try:
        proc = await asyncio.create_subprocess_exec(
            "osascript", "-e", script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=2)
        return "true" in stdout.decode().lower()
    except (asyncio.TimeoutError, OSError):
        return False

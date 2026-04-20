from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Footer, Header, Label, Static

from .models import Session, SessionState
from .scanner import SessionScanner, STATE_DIR
from .widgets import SessionList, StatusBar


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
    #status-bar {
        dock: bottom;
        height: 1;
        background: $accent;
        color: $text;
        padding: 0 1;
    }
    SessionBucket {
        height: auto;
    }
    SessionItem {
        height: 1;
    }
    SessionItem:hover {
        background: $accent 20%;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("enter", "detail", "Detail"),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("down", "cursor_down", "Down", show=False),
        Binding("up", "cursor_up", "Up", show=False),
    ]

    TITLE = "Claude Sessions"

    def __init__(self, standalone: bool = False) -> None:
        self._scanner = SessionScanner()
        self._sessions: list[Session] = []
        self._selected_idx: int = 0
        self._poll_interval: float = 5.0
        self._paused: bool = False
        self._all_stale_since: datetime | None = None
        self._poll_task: asyncio.Task | None = None
        super().__init__()

    def compose(self) -> ComposeResult:
        yield Header()
        yield SessionList(id="session-list")
        yield StatusBar(id="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        self._do_scan()
        self._poll_task = self.set_interval(self._poll_interval, self._poll_tick)

    def _do_scan(self) -> None:
        self._sessions = self._scanner.scan()

        if self._selected_idx >= len(self._sessions):
            self._selected_idx = max(0, len(self._sessions) - 1)

        session_list = self.query_one(SessionList)
        session_list.selected_idx = self._selected_idx
        session_list.sessions = self._sessions

        status_bar = self.query_one(StatusBar)
        status_bar.session_count = len(self._sessions)
        status_bar.poll_interval = self._poll_interval
        status_bar.paused = self._paused

        self._adapt_polling()

    def _adapt_polling(self) -> None:
        if not self._sessions:
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
                    if self._poll_task:
                        self._poll_task.stop()
                    status_bar = self.query_one(StatusBar)
                    status_bar.paused = True
                    return
        else:
            new_interval = 5.0
            self._all_stale_since = None

        if new_interval != self._poll_interval:
            self._poll_interval = new_interval
            if self._poll_task:
                self._poll_task.stop()
            self._poll_task = self.set_interval(self._poll_interval, self._poll_tick)

    def _poll_tick(self) -> None:
        self._do_scan()

    def action_refresh(self) -> None:
        if self._paused:
            self._paused = False
            self._all_stale_since = None
            self._poll_interval = 5.0
            self._poll_task = self.set_interval(self._poll_interval, self._poll_tick)
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

    def action_detail(self) -> None:
        if self._sessions and 0 <= self._selected_idx < len(self._sessions):
            self.push_screen(DetailModal(self._sessions[self._selected_idx]))

    def action_quit(self) -> None:
        self.exit()

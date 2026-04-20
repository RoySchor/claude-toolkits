from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Label, Static

from .models import Session, SessionState

STATE_ICONS = {
    SessionState.COOKING: "🔥",
    SessionState.NEEDS_YOU: "🔔",
    SessionState.RECENTLY_ACTIVE: "✅",
    SessionState.STALE: "💤",
    SessionState.DEAD: "💀",
}

STATE_HEADERS = {
    SessionState.COOKING: "COOKING",
    SessionState.NEEDS_YOU: "NEEDS YOU",
    SessionState.RECENTLY_ACTIVE: "RECENT",
    SessionState.STALE: "STALE",
    SessionState.DEAD: "DEAD",
}

STATE_STYLES = {
    SessionState.COOKING: "bold red",
    SessionState.NEEDS_YOU: "bold yellow",
    SessionState.RECENTLY_ACTIVE: "green",
    SessionState.STALE: "dim",
    SessionState.DEAD: "dim red",
}


class SessionItem(Static):
    DEFAULT_CSS = """
    SessionItem {
        height: 1;
    }
    SessionItem.--selected {
        background: $accent 30%;
    }
    """

    def __init__(self, session: Session, selected: bool = False) -> None:
        self.session = session
        super().__init__()
        if selected:
            self.add_class("--selected")

    def compose(self) -> ComposeResult:
        label = self.session.label
        if self.session.is_unnamed and self.session.state != SessionState.DEAD:
            label = f"[yellow]{label}[/yellow]"

        age_str = ""
        if self.session.age_hours is not None:
            hours = self.session.age_hours
            if hours < 1:
                age_str = f" [dim]{int(hours * 60)}m[/dim]"
            elif hours < 24:
                age_str = f" [dim]{hours:.0f}h[/dim]"
            else:
                age_str = f" [dim]{hours / 24:.0f}d[/dim]"

        marker = "▸ " if self.has_class("--selected") else "  "
        yield Label(f"{marker}{label}{age_str}")


class SessionBucket(Static):
    def __init__(
        self,
        state: SessionState,
        sessions: list[Session],
        collapsed_max: int = 8,
        selected_idx: int = -1,
        start_idx: int = 0,
    ) -> None:
        self.state = state
        self.sessions = sessions
        self.collapsed_max = collapsed_max
        self._selected_idx = selected_idx
        self._start_idx = start_idx
        super().__init__()

    def compose(self) -> ComposeResult:
        icon = STATE_ICONS[self.state]
        header = STATE_HEADERS[self.state]
        style = STATE_STYLES[self.state]
        count = len(self.sessions)

        yield Label(f"[{style}]{icon} {header} ({count})[/{style}]")

        shown = self.sessions[:self.collapsed_max]
        for i, session in enumerate(shown):
            global_idx = self._start_idx + i
            yield SessionItem(session, selected=(global_idx == self._selected_idx))

        remaining = count - len(shown)
        if remaining > 0:
            yield Label(f"  [dim]+{remaining} more...[/dim]")


class SessionList(VerticalScroll):
    sessions: reactive[list[Session]] = reactive(list, recompose=True)
    selected_idx: reactive[int] = reactive(0, recompose=True)

    def compose(self) -> ComposeResult:
        buckets: dict[SessionState, list[Session]] = {}
        for s in self.sessions:
            buckets.setdefault(s.state, []).append(s)

        display_order = [
            SessionState.COOKING,
            SessionState.NEEDS_YOU,
            SessionState.RECENTLY_ACTIVE,
            SessionState.STALE,
        ]

        flat_idx = 0
        any_shown = False
        for state in display_order:
            group = buckets.get(state, [])
            if group:
                any_shown = True
                yield SessionBucket(state, group, selected_idx=self.selected_idx, start_idx=flat_idx)
                flat_idx += len(group)
                yield Label("")

        if not any_shown:
            yield Label("[dim]No active sessions found.[/dim]")


class StatusBar(Static):
    poll_interval: reactive[float] = reactive(5.0)
    session_count: reactive[int] = reactive(0)
    paused: reactive[bool] = reactive(False)

    def render(self) -> str:
        if self.paused:
            return f"⏸  Paused │ {self.session_count} sessions │ [r]esume [q]uit"
        return f"⏸  {self.poll_interval:.0f}s │ {self.session_count} sessions │ [r]efresh [q]uit"

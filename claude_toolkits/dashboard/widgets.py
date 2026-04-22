from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.reactive import reactive
from textual.widgets import Label, Static

from .models import Session, SessionState

STATE_ICONS = {
    SessionState.COOKING: "\U0001f525",
    SessionState.NEEDS_YOU: "\U0001f514",
    SessionState.RECENTLY_ACTIVE: "\u2705",
    SessionState.STALE: "\U0001f4a4",
    SessionState.DEAD: "\U0001f480",
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
        height: auto;
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

        marker = "\u25b8 " if self.has_class("--selected") else "  "
        yield Label(f"{marker}{label}{age_str}")

        summary = self._get_summary()
        if summary:
            yield Label(f"    [dim italic]{summary}[/dim italic]")

    def _get_summary(self) -> str | None:
        s = self.session
        if not s.name:
            return None
        if s.away_summary:
            return s.away_summary.split("\n")[0][:100]
        if s.custom_title and s.custom_title != s.name:
            return s.custom_title[:100]
        return None


class SessionBucket(Static):
    def __init__(
        self,
        state: SessionState,
        sessions: list[Session],
        selected_idx: int = -1,
        start_idx: int = 0,
    ) -> None:
        self.state = state
        self.sessions = sessions
        self._selected_idx = selected_idx
        self._start_idx = start_idx
        super().__init__()

    def compose(self) -> ComposeResult:
        icon = STATE_ICONS[self.state]
        header = STATE_HEADERS[self.state]
        style = STATE_STYLES[self.state]
        count = len(self.sessions)

        yield Label(f"[{style}]{icon} {header} ({count})[/{style}]")

        for i, session in enumerate(self.sessions):
            global_idx = self._start_idx + i
            yield SessionItem(session, selected=(global_idx == self._selected_idx))


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
            SessionState.DEAD,
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
    dead_count: reactive[int] = reactive(0)

    def render(self) -> str:
        if self.paused:
            return f"\u23f8  Paused \u2502 {self.session_count} sessions \u2502 [r]esume [q]uit \u2502 [dim]ctrl+b+tab: Exit Dashboard[/dim]"
        parts = [
            f"\u25b6 {self.poll_interval:.0f}s",
            f"{self.session_count} sessions",
        ]
        if self.dead_count > 0:
            parts.append(f"{self.dead_count} dead")
        parts.append("[r]efresh [q]uit")
        parts.append("[dim]ctrl+b+tab: Exit Dashboard[/dim]")
        return " \u2502 ".join(parts)

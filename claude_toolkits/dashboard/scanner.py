from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import psutil

from .cache import TranscriptCache, has_pending_tool_use
from .models import STALE_THRESHOLD_HOURS, Session, SessionState

CLAUDE_DIR = Path.home() / ".claude"
SESSIONS_DIR = CLAUDE_DIR / "sessions"
PROJECTS_DIR = CLAUDE_DIR / "projects"
STATE_DIR = Path.home() / ".claude-toolkits" / "state"


def is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        proc = psutil.Process(pid)
        cmdline = proc.cmdline()
        if cmdline and "claude" in cmdline[0].lower():
            return True
        exe = proc.exe()
        return "claude" in exe.lower()
    except (ProcessLookupError, psutil.NoSuchProcess, psutil.AccessDenied, IndexError):
        return False


def build_transcript_index() -> dict[str, Path]:
    index: dict[str, Path] = {}
    if not PROJECTS_DIR.exists():
        return index
    for path in PROJECTS_DIR.rglob("*.jsonl"):
        if not path.name.startswith("agent-"):
            index[path.stem] = path
    return index


def load_session_files() -> list[dict]:
    sessions = []
    if not SESSIONS_DIR.exists():
        return sessions
    for f in SESSIONS_DIR.iterdir():
        if f.suffix == ".json":
            try:
                data = json.loads(f.read_text())
                sessions.append(data)
            except (json.JSONDecodeError, OSError):
                continue
    return sessions


def load_hook_states() -> dict[str, dict]:
    states: dict[str, dict] = {}
    if not STATE_DIR.exists():
        return states
    for f in STATE_DIR.iterdir():
        if f.suffix == ".json":
            try:
                data = json.loads(f.read_text())
                sid = data.get("session_id", f.stem)
                states[sid] = data
            except (json.JSONDecodeError, OSError):
                continue
    return states


class SessionScanner:
    def __init__(self) -> None:
        self._transcript_index: dict[str, Path] = {}
        self._caches: dict[str, TranscriptCache] = {}
        self._prev_mtimes: dict[str, float] = {}

    @staticmethod
    def _discover_tmux_sessions() -> tuple[dict[int, str], set[str]]:
        try:
            result = subprocess.run(
                ["tmux", "-L", "ct-sessions", "list-panes", "-a",
                 "-F", "#{session_name} #{pane_pid}"],
                capture_output=True, text=True, timeout=2,
            )
            if result.returncode != 0:
                return {}, set()
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            return {}, set()

        mapping: dict[int, str] = {}
        all_names: set[str] = set()
        for line in result.stdout.strip().splitlines():
            parts = line.rsplit(" ", 1)
            if len(parts) == 2:
                all_names.add(parts[0])
                try:
                    mapping[int(parts[1])] = parts[0]
                except ValueError:
                    continue
        return mapping, all_names

    def scan(self) -> list[Session]:
        self._transcript_index = build_transcript_index()
        session_files = load_session_files()
        hook_states = load_hook_states()
        tmux_map, all_ct_names = self._discover_tmux_sessions()

        sessions: list[Session] = []
        seen_ids: set[str] = set()

        for raw in session_files:
            sid = raw.get("sessionId", "")
            if not sid:
                continue
            seen_ids.add(sid)

            pid = raw.get("pid")
            alive = is_alive(pid) if pid else False

            session = Session(
                session_id=sid,
                pid=pid,
                cwd=raw.get("cwd", ""),
                name=raw.get("name"),
                started_at=self._parse_started_at(raw.get("startedAt")),
                transcript_path=self._transcript_index.get(sid),
            )

            if pid and pid in tmux_map:
                session.tmux_session_name = tmux_map[pid]

            if not alive:
                session.state = SessionState.DEAD
                if sid in hook_states:
                    self._cleanup_state_file(sid)
                sessions.append(session)
                continue

            if sid in hook_states:
                self._apply_hook_state(session, hook_states[sid])
            else:
                self._apply_fallback_state(session)

            sessions.append(session)

        for sid, state_data in hook_states.items():
            if sid not in seen_ids:
                session = Session(
                    session_id=sid,
                    cwd=state_data.get("cwd", ""),
                    source="hook",
                )
                self._apply_hook_state(session, state_data)
                sessions.append(session)

        claimed_tmux_names = {s.tmux_session_name for s in sessions if s.tmux_session_name}
        for name in sorted(all_ct_names):
            if not name.startswith("ct-") and name not in claimed_tmux_names:
                sessions.append(Session(
                    session_id=f"tmux-shell-{name}",
                    state=SessionState.SHELL,
                    source="tmux",
                    tmux_session_name=name,
                    is_shell=True,
                ))

        sessions.sort(key=lambda s: (self._state_sort_key(s.state), s.label.lower()))
        return sessions

    def _apply_hook_state(self, session: Session, state_data: dict) -> None:
        session.source = "hook"
        raw_state = state_data.get("state", "idle")
        ts_str = state_data.get("timestamp")

        if ts_str:
            try:
                session.last_activity = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            except ValueError:
                pass

        if raw_state == "cooking":
            session.state = SessionState.COOKING
        elif raw_state == "needs_input":
            session.state = SessionState.NEEDS_YOU
        elif raw_state == "idle":
            if session.transcript_path and has_pending_tool_use(session.transcript_path):
                session.state = SessionState.NEEDS_YOU
            elif session.age_hours is not None and session.age_hours > STALE_THRESHOLD_HOURS:
                session.state = SessionState.STALE
            else:
                session.state = SessionState.RECENTLY_ACTIVE
        else:
            session.state = SessionState.RECENTLY_ACTIVE

        self._load_labels(session)

    def _apply_fallback_state(self, session: Session) -> None:
        session.source = "fallback"
        tp = session.transcript_path
        if tp is None:
            session.state = SessionState.STALE
            return

        sid = session.session_id
        if sid not in self._caches:
            cache = TranscriptCache(path=tp)
            cache.initial_load()
            self._caches[sid] = cache
        else:
            cache = self._caches[sid]
            if cache.path != tp:
                cache = TranscriptCache(path=tp)
                cache.initial_load()
                self._caches[sid] = cache

        current_mtime = self._get_mtime(tp)
        prev_mtime = self._prev_mtimes.get(sid, 0.0)

        if prev_mtime > 0 and current_mtime > prev_mtime:
            session.state = SessionState.COOKING
        elif cache.last_user_assistant:
            ts_str = cache.last_user_assistant.get("timestamp", "")
            if ts_str:
                try:
                    last_ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    session.last_activity = last_ts
                    hours = (datetime.now(timezone.utc) - last_ts).total_seconds() / 3600
                    if hours > STALE_THRESHOLD_HOURS:
                        session.state = SessionState.STALE
                    elif has_pending_tool_use(tp):
                        session.state = SessionState.NEEDS_YOU
                    else:
                        session.state = SessionState.RECENTLY_ACTIVE
                except ValueError:
                    session.state = SessionState.STALE
            else:
                session.state = SessionState.STALE
        else:
            session.state = SessionState.STALE

        self._prev_mtimes[sid] = current_mtime

        session.custom_title = cache.custom_title
        session.away_summary = cache.away_summary

    def _load_labels(self, session: Session) -> None:
        tp = session.transcript_path
        if tp is None:
            return
        sid = session.session_id
        if sid not in self._caches:
            cache = TranscriptCache(path=tp)
            cache.initial_load()
            self._caches[sid] = cache
        cache = self._caches[sid]
        session.custom_title = cache.custom_title
        session.away_summary = cache.away_summary

    @staticmethod
    def _cleanup_state_file(session_id: str) -> None:
        state_file = STATE_DIR / f"{session_id}.json"
        try:
            state_file.unlink(missing_ok=True)
        except OSError:
            pass

    @staticmethod
    def _get_mtime(path: Path) -> float:
        try:
            return os.stat(path).st_mtime
        except OSError:
            return 0.0

    @staticmethod
    def _parse_started_at(value) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return None
        return None

    @staticmethod
    def _state_sort_key(state: SessionState) -> int:
        order = {
            SessionState.COOKING: 0,
            SessionState.NEEDS_YOU: 1,
            SessionState.RECENTLY_ACTIVE: 2,
            SessionState.SHELL: 3,
            SessionState.STALE: 4,
            SessionState.DEAD: 5,
        }
        return order.get(state, 5)

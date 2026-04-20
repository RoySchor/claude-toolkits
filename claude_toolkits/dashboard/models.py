from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


class SessionState(enum.Enum):
    COOKING = "cooking"
    NEEDS_YOU = "needs_you"
    RECENTLY_ACTIVE = "recently_active"
    STALE = "stale"
    DEAD = "dead"


STALE_THRESHOLD_HOURS = 12


@dataclass
class Session:
    session_id: str
    pid: int | None = None
    cwd: str = ""
    name: str | None = None
    started_at: datetime | None = None
    state: SessionState = SessionState.STALE
    last_activity: datetime | None = None
    transcript_path: Path | None = None
    custom_title: str | None = None
    away_summary: str | None = None
    source: str = "fallback"  # "hook" or "fallback"

    @property
    def label(self) -> str:
        if self.name:
            return self.name
        if self.custom_title:
            return self.custom_title[:30]
        if self.away_summary:
            first_line = self.away_summary.split("\n")[0]
            return first_line[:30]
        if self.cwd:
            return Path(self.cwd).name
        return "(unnamed)"

    @property
    def is_unnamed(self) -> bool:
        return self.name is None

    @property
    def age_hours(self) -> float | None:
        if self.last_activity is None:
            return None
        delta = datetime.now(timezone.utc) - self.last_activity
        return delta.total_seconds() / 3600

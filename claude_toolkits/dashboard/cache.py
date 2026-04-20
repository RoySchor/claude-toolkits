from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class TranscriptCache:
    path: Path
    last_size: int = 0
    last_mtime: float = 0.0
    last_user_assistant: dict | None = None
    away_summary: str | None = None
    custom_title: str | None = None

    def needs_update(self) -> bool:
        try:
            stat = os.stat(self.path)
        except OSError:
            return False
        return stat.st_size != self.last_size or stat.st_mtime != self.last_mtime

    def is_growing(self) -> bool:
        try:
            stat = os.stat(self.path)
        except OSError:
            return False
        return stat.st_size > self.last_size and self.last_size > 0

    def read_new_entries(self) -> list[dict]:
        try:
            stat = os.stat(self.path)
        except OSError:
            return []

        if stat.st_size <= self.last_size:
            self.last_mtime = stat.st_mtime
            return []

        entries = []
        with open(self.path, "r") as f:
            if self.last_size > 0:
                f.seek(self.last_size)
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    entries.append(entry)
                except json.JSONDecodeError:
                    continue

        self.last_size = stat.st_size
        self.last_mtime = stat.st_mtime
        return entries

    def initial_load(self) -> None:
        if not self.path.exists():
            return

        file_size = self.path.stat().st_size
        chunk_size = 50 * 1024

        with open(self.path, "rb") as f:
            offset = max(0, file_size - chunk_size)
            while offset >= 0:
                f.seek(offset)
                chunk = f.read(min(chunk_size, file_size - offset))
                lines = chunk.decode("utf-8", errors="replace").split("\n")

                for line in reversed(lines):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    entry_type = entry.get("type")
                    if entry_type in ("user", "assistant"):
                        if self.last_user_assistant is None:
                            self.last_user_assistant = entry
                    elif entry_type == "system" and entry.get("subtype") == "away_summary":
                        if self.away_summary is None:
                            content = entry.get("content", "")
                            if isinstance(content, list):
                                for block in content:
                                    if isinstance(block, dict) and block.get("type") == "text":
                                        self.away_summary = block.get("text", "")[:60]
                                        break
                            elif isinstance(content, str):
                                self.away_summary = content[:60]
                    elif entry_type == "custom-title":
                        if self.custom_title is None:
                            self.custom_title = entry.get("title", "")

                    if self.last_user_assistant is not None:
                        break

                if self.last_user_assistant is not None:
                    break

                if offset == 0:
                    break
                offset = max(0, offset - chunk_size)

        stat = os.stat(self.path)
        self.last_size = stat.st_size
        self.last_mtime = stat.st_mtime


def has_pending_tool_use(transcript_path: Path) -> bool:
    if not transcript_path.exists():
        return False

    file_size = transcript_path.stat().st_size
    chunk_size = 50 * 1024

    with open(transcript_path, "rb") as f:
        offset = max(0, file_size - chunk_size)
        f.seek(offset)
        chunk = f.read().decode("utf-8", errors="replace")

    lines = chunk.strip().split("\n")

    last_assistant = None
    has_tool_result = False

    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue

        entry_type = entry.get("type")
        if entry_type == "assistant" and last_assistant is None:
            last_assistant = entry
        elif entry_type == "user":
            break

    if last_assistant is None:
        return False

    message = last_assistant.get("message", {})
    content = message.get("content", [])
    if not isinstance(content, list):
        return False

    has_tool_use = any(
        isinstance(block, dict) and block.get("type") == "tool_use"
        for block in content
    )

    if not has_tool_use:
        return False

    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get("type") == "user":
            message = entry.get("message", {})
            content = message.get("content", [])
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        return False
            break

    return True

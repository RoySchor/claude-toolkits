from __future__ import annotations

import json
import subprocess
from pathlib import Path

PROJECTS_DIR = Path.home() / ".claude" / "projects"


def find_transcript(session_id: str) -> Path | None:
    if not PROJECTS_DIR.exists():
        return None
    for path in PROJECTS_DIR.rglob("*.jsonl"):
        if path.stem == session_id and not path.name.startswith("agent-"):
            return path
    return None


def extract_user_prompts(transcript_path: Path, max_prompts: int = 8) -> list[str]:
    prompts: list[str] = []
    try:
        with open(transcript_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if entry.get("type") == "user":
                    msg = entry.get("message", {})
                    if isinstance(msg, dict):
                        content = msg.get("content", "")
                        if isinstance(content, list):
                            text_parts = [
                                p.get("text", "")
                                for p in content
                                if isinstance(p, dict) and p.get("type") == "text"
                            ]
                            content = "\n".join(text_parts)
                    else:
                        content = str(msg)
                    if content.strip():
                        prompts.append(content.strip()[:300])
    except OSError:
        pass
    return prompts[-max_prompts:]


def discover_pr(cwd: str) -> str | None:
    try:
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=5, cwd=cwd,
        )
        if branch.returncode != 0:
            return None
        branch_name = branch.stdout.strip()
        if branch_name in ("main", "master", "HEAD"):
            return None

        result = subprocess.run(
            ["gh", "pr", "list", "--head", branch_name, "--state", "open",
             "--json", "url", "--limit", "1"],
            capture_output=True, text=True, timeout=10, cwd=cwd,
        )
        if result.returncode != 0:
            return None
        prs = json.loads(result.stdout)
        if prs:
            return prs[0].get("url")
    except (OSError, json.JSONDecodeError, subprocess.TimeoutExpired):
        pass
    return None


def get_git_log(cwd: str, max_commits: int = 20) -> str:
    try:
        base = subprocess.run(
            ["git", "merge-base", "HEAD", "origin/main"],
            capture_output=True, text=True, timeout=5, cwd=cwd,
        )
        if base.returncode != 0:
            base = subprocess.run(
                ["git", "merge-base", "HEAD", "origin/master"],
                capture_output=True, text=True, timeout=5, cwd=cwd,
            )
        if base.returncode == 0:
            merge_base = base.stdout.strip()
            result = subprocess.run(
                ["git", "log", "--oneline", f"{merge_base}..HEAD", f"--max-count={max_commits}"],
                capture_output=True, text=True, timeout=5, cwd=cwd,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()

        result = subprocess.run(
            ["git", "log", "--oneline", f"-{max_commits}"],
            capture_output=True, text=True, timeout=5, cwd=cwd,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return ""


def build_review_brief(
    session_name: str,
    cwd: str,
    pr_url: str | None,
    transcript_path: Path | None,
    away_summary: str | None,
) -> str:
    sections = []

    sections.append(f"# Adversarial PR Review: {session_name}")
    sections.append("")
    sections.append(
        "You are reviewing code written by another Claude session. "
        "Your job is to find bugs, questionable assumptions, missed edge cases, "
        "and security issues. Be thorough and adversarial — the original author "
        "may have been too close to the problem."
    )
    sections.append("")

    if pr_url:
        sections.append("## PR to Review")
        sections.append(f"URL: {pr_url}")
        sections.append("Use `gh pr diff` and `gh pr view` to examine the changes.")
    else:
        sections.append("## Review Target")
        sections.append(
            "No open PR found. Review the local uncommitted/committed changes on the current branch."
        )
        sections.append("Use `git diff` and `git log` to examine what changed.")

    sections.append("")
    sections.append("## Working Directory")
    sections.append(f"`{cwd}`")

    git_log = get_git_log(cwd)
    if git_log:
        sections.append("")
        sections.append("## Branch Commits")
        sections.append("```")
        sections.append(git_log)
        sections.append("```")

    if away_summary:
        sections.append("")
        sections.append("## Session Summary (from original author)")
        sections.append(away_summary)

    if transcript_path:
        prompts = extract_user_prompts(transcript_path)
        if prompts:
            sections.append("")
            sections.append("## Original User Prompts (what the author was asked to do)")
            for i, p in enumerate(prompts, 1):
                sections.append(f"\n### Prompt {i}")
                sections.append(p)

    sections.append("")
    sections.append("## Your Task")
    sections.append("1. Read the PR diff (or local changes)")
    sections.append("2. Identify bugs, edge cases, security issues, or incorrect assumptions")
    sections.append("3. Check that the implementation matches what was asked")
    sections.append("4. Look for things the original author might have missed or gotten wrong")
    sections.append("5. Summarize your findings clearly")

    return "\n".join(sections)

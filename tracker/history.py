"""История каталога данных: каждая запись - git-коммит, сбой git запись не отменяет."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)

AUTHOR = "task-tracker"
EMAIL = "task-tracker@localhost"
TIMEOUT = 20


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    # safe.directory на каждый вызов для тома другого владельца.
    return subprocess.run(
        [
            "git",
            "-c", f"user.name={AUTHOR}",
            "-c", f"user.email={EMAIL}",
            "-c", f"safe.directory={root}",
            "-C", str(root),
            *args,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=TIMEOUT,
        check=False,
    )


def _ensure(root: Path) -> bool:
    if (root / ".git").exists():
        return True
    result = _git(root, "init", "-q")
    if result.returncode != 0:
        log.warning("git init не удался: %s", result.stderr[:200])
        return False
    _git(root, "symbolic-ref", "HEAD", "refs/heads/main")
    return True


def commit(root: Path, message: str) -> bool:
    try:
        if not _ensure(root):
            return False
        _git(root, "add", "-A")
        result = _git(root, "commit", "-q", "-m", message)
    except (OSError, subprocess.SubprocessError) as error:
        log.warning("git недоступен: %s", str(error)[:200])
        return False
    if result.returncode != 0:
        output = result.stdout + result.stderr
        if "nothing to commit" not in output:
            log.warning("git commit не удался: %s", output[:200])
        return False
    return True

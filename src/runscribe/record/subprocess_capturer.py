"""M1 capturer: run each command via ``subprocess`` and capture its result.

This is deliberately simple and fully cross-platform (Windows/macOS/Linux). Each
command runs in its own shell process, so shell state that would normally persist
(``cd``, ``export``) does not carry over automatically. We special-case ``cd`` —
the one piece of state a runbook almost always needs — by tracking the working
directory ourselves. Fuller shell fidelity (aliases, ``export``, interactive TUIs)
is the job of the M2 PTY capturer.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

from .capturer import Capturer, CommandResult

# Keep captured output bounded so a chatty command (npm install, docker pull)
# can't bloat the session file or a rendered runbook.
_MAX_OUTPUT_CHARS = 20_000
_TRUNCATION_MARKER = "\n... [output truncated by runscribe] ..."


class SubprocessCapturer(Capturer):
    def __init__(self, cwd: str | None = None) -> None:
        self._cwd = str(Path(cwd).resolve()) if cwd else os.getcwd()

    @property
    def cwd(self) -> str:
        return self._cwd

    def run(self, command: str) -> CommandResult:
        stripped = command.strip()
        builtin = self._try_builtin(stripped)
        if builtin is not None:
            return builtin

        start = time.monotonic()
        completed = subprocess.run(
            stripped,
            shell=True,
            cwd=self._cwd,
            capture_output=True,
            text=True,
        )
        duration_ms = int((time.monotonic() - start) * 1000)
        output = _combine(completed.stdout, completed.stderr)
        return CommandResult(
            output=_truncate(output),
            exit_code=completed.returncode,
            duration_ms=duration_ms,
            cwd=self._cwd,
        )

    def _try_builtin(self, command: str) -> CommandResult | None:
        """Handle ``cd`` ourselves so directory changes persist across steps."""
        if command != "cd" and not command.startswith(("cd ", "cd\t")):
            return None
        arg = command[2:].strip()
        target = Path.home() if arg in ("", "~") else Path(self._cwd, os.path.expanduser(arg))
        try:
            resolved = target.resolve(strict=True)
            if not resolved.is_dir():
                raise NotADirectoryError(resolved)
            self._cwd = str(resolved)
            return CommandResult(output="", exit_code=0, duration_ms=0, cwd=self._cwd)
        except (FileNotFoundError, NotADirectoryError):
            return CommandResult(
                output=f"cd: no such directory: {arg}",
                exit_code=1,
                duration_ms=0,
                cwd=self._cwd,
            )


def _combine(stdout: str, stderr: str) -> str:
    parts = [p for p in (stdout, stderr) if p]
    return "\n".join(parts).rstrip("\n")


def _truncate(output: str) -> str:
    if len(output) <= _MAX_OUTPUT_CHARS:
        return output
    return output[:_MAX_OUTPUT_CHARS] + _TRUNCATION_MARKER

"""A capturer that keeps one shell alive for the whole session.

M1's :class:`~runscribe.record.subprocess_capturer.SubprocessCapturer` runs each
command in a fresh process, so ``cd``, ``export``, and shell variables don't
carry over — a real limitation for runbooks that set up state and then use it.
This capturer feeds commands to a single long-lived POSIX shell and reads back
output using a unique sentinel line that also reports the exit code and working
directory. State therefore persists exactly as it would in a normal session.

Scope: POSIX shells (``bash``/``sh``). Windows keeps the subprocess capturer for
now (see :func:`runscribe.record.make_capturer`); a native Windows persistent
shell and full interactive-TUI (PTY) capture are tracked for later. Commands that
read from stdin interactively (e.g. a bare ``cat``) are not supported here.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time
from pathlib import Path

from .capturer import Capturer, CommandResult

# Time budget for the shell to prove it can run a command and echo the sentinel.
# If it exceeds this (or dies), we treat the shell as unusable and fall back.
_STARTUP_PROBE_TIMEOUT_S = 5.0

# A distinctive line the user's own output is overwhelmingly unlikely to emit.
# Printed after every command as: "<SENTINEL> <exit_code> <cwd>".
_SENTINEL = "__RUNSCRIBE_STEP_END_9f2c1a__"

_MAX_OUTPUT_CHARS = 20_000
_TRUNCATION_MARKER = "\n... [output truncated by runscribe] ..."


def default_posix_shell() -> str | None:
    """Return a usable POSIX shell path, or ``None`` if none is available.

    On Windows this deliberately skips ``C:\\Windows\\System32\\bash.exe`` — that
    is the WSL launcher stub, not a pipe-driveable POSIX shell; if WSL isn't set
    up it exits immediately. A real ``bash``/``sh`` (e.g. Git for Windows) is fine.
    """
    candidates: list[str] = []
    env_shell = os.environ.get("SHELL")
    if env_shell and Path(env_shell).name.removesuffix(".exe") in {"bash", "sh", "zsh"}:
        candidates.append(env_shell)
    for name in ("bash", "sh"):
        found = shutil.which(name)
        if found:
            candidates.append(found)

    for path in candidates:
        if "system32" in path.lower():  # WSL stub — not usable here
            continue
        if Path(path).exists():
            return path
    return None


class PersistentShellError(RuntimeError):
    """The persistent shell could not be started or died unexpectedly."""


class PersistentShellCapturer(Capturer):
    def __init__(self, shell: str | None = None, cwd: str | None = None) -> None:
        resolved = shell or default_posix_shell()
        if resolved is None:
            raise PersistentShellError("no POSIX shell (bash/sh) found on PATH")
        self._shell = resolved
        start_cwd = str(Path(cwd).resolve()) if cwd else os.getcwd()
        # A pipe (not a TTY) means the shell runs non-interactively and prints no
        # prompt, so nothing pollutes the captured output. stderr is merged into
        # stdout because a runbook wants the whole story of each step, in order.
        self._proc = subprocess.Popen(
            [self._shell],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            encoding="utf-8",
            errors="replace",
            cwd=start_cwd,
            env={**os.environ, "PS1": "", "PS2": ""},
        )
        self._cwd = start_cwd
        self._verify_startup()

    def _verify_startup(self) -> None:
        """Run a no-op through the shell to confirm it actually works.

        A shell that exits immediately (e.g. the WSL stub, or a mis-detected
        binary) is caught here so callers can fall back cleanly instead of
        failing on the user's first real command. Bounded by a watchdog so a
        hung shell can't wedge startup.
        """
        watchdog = threading.Timer(_STARTUP_PROBE_TIMEOUT_S, self._proc.kill)
        watchdog.start()
        try:
            self.run(":")  # POSIX no-op; also seeds self._cwd from the shell's $PWD
        except PersistentShellError:
            self.close()
            raise
        finally:
            watchdog.cancel()

    @property
    def cwd(self) -> str:
        return self._cwd

    def run(self, command: str) -> CommandResult:
        if self._proc.poll() is not None or self._proc.stdin is None or self._proc.stdout is None:
            raise PersistentShellError("the shell has exited")

        start = time.monotonic()
        # Run the command, then emit the sentinel carrying that command's exit
        # code ($?) and the resulting working directory ($PWD).
        try:
            self._proc.stdin.write(command + "\n")
            self._proc.stdin.write(f'printf "\\n%s %s %s\\n" "{_SENTINEL}" "$?" "$PWD"\n')
            self._proc.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise PersistentShellError("the shell closed its input") from exc

        output_lines: list[str] = []
        exit_code = 0
        while True:
            line = self._proc.stdout.readline()
            if line == "":  # shell closed its output — treat as death
                raise PersistentShellError("the shell exited mid-command")
            if line.lstrip().startswith(_SENTINEL):
                exit_code, self._cwd = _parse_sentinel(line, self._cwd)
                break
            output_lines.append(line.rstrip("\n"))

        duration_ms = int((time.monotonic() - start) * 1000)
        output = "\n".join(output_lines).strip("\n")
        return CommandResult(
            output=_truncate(output),
            exit_code=exit_code,
            duration_ms=duration_ms,
            cwd=self._cwd,
        )

    def close(self) -> None:
        if self._proc.poll() is None:
            try:
                if self._proc.stdin is not None:
                    self._proc.stdin.close()
                self._proc.terminate()
                self._proc.wait(timeout=3)
            except (OSError, subprocess.TimeoutExpired):  # pragma: no cover - best effort
                self._proc.kill()


def _parse_sentinel(line: str, fallback_cwd: str) -> tuple[int, str]:
    # Format: "<SENTINEL> <exit_code> <cwd...>"; cwd may contain spaces.
    parts = line.strip().split(" ", 2)
    exit_code = int(parts[1]) if len(parts) > 1 and parts[1].lstrip("-").isdigit() else 0
    cwd = parts[2] if len(parts) > 2 and parts[2] else fallback_cwd
    return exit_code, cwd


def _truncate(output: str) -> str:
    if len(output) <= _MAX_OUTPUT_CHARS:
        return output
    return output[:_MAX_OUTPUT_CHARS] + _TRUNCATION_MARKER

"""PTY-backed capturer (POSIX only) — highest-fidelity capture.

Runs the session shell attached to a real pseudo-terminal, so programs that
check ``isatty`` behave as they would in a normal terminal (colored output,
progress bars, and simple interactive prompts). Like
:class:`~runscribe.record.persistent_capturer.PersistentShellCapturer` it keeps
one shell alive and delimits each command's output with a unique sentinel that
also reports the exit code and working directory.

This is opt-in (`runscribe record --pty`); the pipe-based persistent capturer
remains the default because it is simpler and already carries shell state.
Windows (ConPTY) is not supported yet — construction raises on non-POSIX so the
factory can fall back cleanly.
"""

from __future__ import annotations

import os
import re
import select
import subprocess
import sys
import threading
import time
from pathlib import Path

from .capturer import Capturer, CommandResult
from .persistent_capturer import PersistentShellError, default_posix_shell

_POSIX = sys.platform != "win32"
if _POSIX:
    import termios

# On a PTY the shell runs interactively, so readline emits terminal control
# sequences (bracketed-paste toggles \x1b[?2004h/l, colors, cursor moves, window
# titles). Strip them so captured output is clean text, not raw escapes.
_ANSI_RE = re.compile(
    r"\x1b\[[0-9;?]*[ -/]*[@-~]"  # CSI: ESC [ ... final byte
    r"|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)"  # OSC: ESC ] ... BEL or ST
    r"|\x1b[@-Z\\-_]"  # other two-character escapes
)

_SENTINEL = "__RUNSCRIBE_PTY_END_4b8e2d__"
_STARTUP_PROBE_TIMEOUT_S = 5.0
_MAX_OUTPUT_CHARS = 20_000
_TRUNCATION_MARKER = "\n... [output truncated by runscribe] ..."


def pty_supported() -> bool:
    return _POSIX and default_posix_shell() is not None


class PtyCapturer(Capturer):
    def __init__(self, shell: str | None = None) -> None:
        if not _POSIX:
            raise PersistentShellError("PTY capture is not supported on Windows yet")
        resolved = shell or default_posix_shell()
        if resolved is None:
            raise PersistentShellError("no POSIX shell (bash/sh) found on PATH")

        import pty  # local import: module is absent on Windows

        self._master, slave = pty.openpty()
        _disable_echo(slave)
        args = [resolved]
        if Path(resolved).name.removesuffix(".exe") == "bash":
            args += ["--norc", "--noprofile"]
        self._proc = subprocess.Popen(
            args,
            stdin=slave,
            stdout=slave,
            stderr=slave,
            start_new_session=True,
            env={**os.environ, "PS1": "", "PS2": "", "TERM": "xterm-256color"},
        )
        os.close(slave)
        self._cwd = os.getcwd()
        self._verify_startup()

    def _verify_startup(self) -> None:
        watchdog = threading.Timer(_STARTUP_PROBE_TIMEOUT_S, self._proc.kill)
        watchdog.start()
        try:
            self.run(":")  # POSIX no-op; also seeds cwd from the shell's $PWD
        except PersistentShellError:
            self.close()
            raise
        finally:
            watchdog.cancel()

    @property
    def cwd(self) -> str:
        return self._cwd

    def run(self, command: str) -> CommandResult:
        if self._proc.poll() is not None:
            raise PersistentShellError("the shell has exited")

        start = time.monotonic()
        payload = f'{command}\nprintf "\\n%s %s %s\\n" "{_SENTINEL}" "$?" "$PWD"\n'
        try:
            os.write(self._master, payload.encode("utf-8"))
        except OSError as exc:
            raise PersistentShellError("the shell closed its input") from exc

        buffer = ""
        while _SENTINEL not in buffer:
            ready, _, _ = select.select([self._master], [], [], 1.0)
            if not ready:
                if self._proc.poll() is not None:
                    raise PersistentShellError("the shell exited mid-command")
                continue
            try:
                chunk = os.read(self._master, 4096)
            except OSError:  # EIO once the child closes the pty
                raise PersistentShellError("the shell exited mid-command") from None
            if not chunk:
                raise PersistentShellError("the shell exited mid-command")
            buffer += chunk.decode("utf-8", errors="replace")

        output, exit_code = self._split_on_sentinel(buffer)
        duration_ms = int((time.monotonic() - start) * 1000)
        return CommandResult(
            output=_truncate(output),
            exit_code=exit_code,
            duration_ms=duration_ms,
            cwd=self._cwd,
        )

    def _split_on_sentinel(self, buffer: str) -> tuple[str, int]:
        # Strip terminal control sequences, then normalise \r\n before parsing.
        clean = _ANSI_RE.sub("", buffer).replace("\r\n", "\n")
        lines = clean.split("\n")
        output_lines: list[str] = []
        exit_code = 0
        for line in lines:
            if line.lstrip().startswith(_SENTINEL):
                parts = line.strip().split(" ", 2)
                if len(parts) > 1 and parts[1].lstrip("-").isdigit():
                    exit_code = int(parts[1])
                if len(parts) > 2 and parts[2]:
                    self._cwd = parts[2]
                break
            output_lines.append(line)
        return "\n".join(output_lines).strip("\n"), exit_code

    def close(self) -> None:
        if self._proc.poll() is None:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=3)
            except (OSError, subprocess.TimeoutExpired):  # pragma: no cover - best effort
                self._proc.kill()
        try:
            os.close(self._master)
        except OSError:  # pragma: no cover - already closed
            pass


def _disable_echo(fd: int) -> None:
    """Turn off terminal echo so the master doesn't read back the commands we write."""
    attrs = termios.tcgetattr(fd)
    attrs[3] &= ~termios.ECHO  # lflags
    termios.tcsetattr(fd, termios.TCSANOW, attrs)


def _truncate(output: str) -> str:
    if len(output) <= _MAX_OUTPUT_CHARS:
        return output
    return output[:_MAX_OUTPUT_CHARS] + _TRUNCATION_MARKER

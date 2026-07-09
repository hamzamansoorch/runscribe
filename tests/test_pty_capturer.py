"""PTY capturer (POSIX only; skipped on Windows and where no shell is available).

These run on the Linux/macOS CI matrix. On Windows the PTY capturer is
unsupported by design, so the whole module skips.
"""

from __future__ import annotations

import pytest

from runscribe.record import PtyCapturer, make_capturer, pty_supported
from runscribe.record.pty_capturer import PtyCapturer as _PtyCapturer


def _works() -> bool:
    if not pty_supported():
        return False
    try:
        _PtyCapturer().close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _works(), reason="PTY capture unavailable on this platform")


def test_output_and_exit_code() -> None:
    cap = PtyCapturer()
    try:
        result = cap.run("echo hello-pty")
        assert result.output.strip() == "hello-pty"
        assert result.exit_code == 0
        assert cap.run("false").exit_code == 1
    finally:
        cap.close()


def test_state_persists_across_commands() -> None:
    cap = PtyCapturer()
    try:
        assert cap.run("export RS_PTY=works").exit_code == 0
        assert cap.run("echo $RS_PTY").output.strip() == "works"
    finally:
        cap.close()


def test_cwd_tracks_cd() -> None:
    cap = PtyCapturer()
    try:
        cap.run("cd /")
        assert cap.cwd == "/"
    finally:
        cap.close()


def test_reports_tty_to_child() -> None:
    # The whole point of PTY capture: programs see a terminal.
    cap = PtyCapturer()
    try:
        result = cap.run("test -t 1 && echo IS_TTY || echo NOT_TTY")
        assert result.output.strip() == "IS_TTY"
    finally:
        cap.close()


def test_make_capturer_pty() -> None:
    cap = make_capturer(pty=True)
    try:
        assert isinstance(cap, PtyCapturer)
    finally:
        cap.close()

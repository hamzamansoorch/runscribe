"""Persistent-shell capturer: state persists across commands (POSIX only)."""

from __future__ import annotations

import pytest

from runscribe.record import (
    PersistentShellCapturer,
    PersistentShellError,
    SubprocessCapturer,
    make_capturer,
)


def _persistent_shell_works() -> bool:
    """True only if a POSIX shell is present *and* drives our pipe correctly.

    On Windows without a real bash (only the WSL stub, or nothing) this is
    False, so these POSIX-only tests skip instead of failing.
    """
    try:
        PersistentShellCapturer().close()
        return True
    except (PersistentShellError, OSError):
        return False


pytestmark = pytest.mark.skipif(
    not _persistent_shell_works(), reason="no working POSIX shell for persistent capture"
)


def test_exported_variable_persists_across_commands() -> None:
    cap = PersistentShellCapturer()
    try:
        assert cap.run("export RS_TEST_VAR=persisted").exit_code == 0
        result = cap.run("echo $RS_TEST_VAR")
        assert result.output.strip() == "persisted"
    finally:
        cap.close()


def test_exit_codes_are_captured() -> None:
    cap = PersistentShellCapturer()
    try:
        assert cap.run("true").exit_code == 0
        assert cap.run("false").exit_code == 1
    finally:
        cap.close()


def test_cwd_tracks_cd() -> None:
    cap = PersistentShellCapturer()
    try:
        cap.run("cd /")
        assert cap.cwd == "/"
    finally:
        cap.close()


def test_output_is_captured() -> None:
    cap = PersistentShellCapturer()
    try:
        assert cap.run("echo hello-persistent").output.strip() == "hello-persistent"
    finally:
        cap.close()


def test_make_capturer_force_subprocess() -> None:
    assert isinstance(make_capturer(persistent=False), SubprocessCapturer)


def test_make_capturer_force_persistent() -> None:
    cap = make_capturer(persistent=True)
    try:
        assert isinstance(cap, PersistentShellCapturer)
    finally:
        cap.close()

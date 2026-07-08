"""Subprocess capturer runs commands cross-platform and tracks cwd via `cd`."""

from __future__ import annotations

from pathlib import Path

from runscribe.record import SubprocessCapturer


def test_echo_captures_output_and_exit_code() -> None:
    cap = SubprocessCapturer()
    result = cap.run("echo hello-runscribe")
    assert "hello-runscribe" in result.output
    assert result.exit_code == 0
    assert result.duration_ms >= 0


def test_nonzero_exit_code() -> None:
    cap = SubprocessCapturer()
    # `exit 3` is understood by both cmd.exe and POSIX shells.
    result = cap.run("exit 3")
    assert result.exit_code == 3


def test_cd_builtin_changes_cwd(tmp_path: Path) -> None:
    sub = tmp_path / "child"
    sub.mkdir()
    cap = SubprocessCapturer(cwd=str(tmp_path))
    result = cap.run("cd child")
    assert result.exit_code == 0
    assert Path(cap.cwd) == sub.resolve()


def test_cd_into_missing_dir_fails() -> None:
    cap = SubprocessCapturer()
    before = cap.cwd
    result = cap.run("cd this-directory-should-not-exist-xyz")
    assert result.exit_code == 1
    assert cap.cwd == before  # cwd unchanged on failure

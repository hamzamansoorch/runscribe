"""Session model round-trips through JSONL without loss."""

from __future__ import annotations

from pathlib import Path

from runscribe.session import SessionWriter, Step, StepKind, read_session


def test_write_then_read_roundtrip(tmp_path: Path) -> None:
    steps = [
        Step(index=0, kind=StepKind.SECTION, text="Deploy"),
        Step(index=1, kind=StepKind.NOTE, text="check the tag"),
        Step(
            index=2,
            kind=StepKind.COMMAND,
            text="git status",
            cwd="/repo",
            exit_code=0,
            started_at="2026-07-06T14:00:00",
            duration_ms=42,
            output="clean",
        ),
    ]
    path = tmp_path / "s.jsonl"
    with SessionWriter(path) as writer:
        for step in steps:
            writer.append(step)

    loaded = read_session(path)
    assert loaded == steps
    assert loaded[2].kind is StepKind.COMMAND


def test_read_skips_blank_lines(tmp_path: Path) -> None:
    path = tmp_path / "s.jsonl"
    with SessionWriter(path) as writer:
        writer.append(Step(index=0, kind=StepKind.COMMAND, text="echo hi", exit_code=0))
    path.write_text(path.read_text(encoding="utf-8") + "\n\n", encoding="utf-8")

    loaded = read_session(path)
    assert len(loaded) == 1


def test_append_is_incremental(tmp_path: Path) -> None:
    path = tmp_path / "s.jsonl"
    writer = SessionWriter(path)
    writer.append(Step(index=0, kind=StepKind.NOTE, text="first"))
    # Simulate a crash: the file should already hold the first step.
    assert len(read_session(path)) == 1
    writer.append(Step(index=1, kind=StepKind.NOTE, text="second"))
    writer.close()
    assert len(read_session(path)) == 2

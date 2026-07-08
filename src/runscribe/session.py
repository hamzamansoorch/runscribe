"""Session data model and crash-safe JSONL persistence.

A *session* is one recording: an ordered list of :class:`Step` objects written
to a ``.jsonl`` file, one JSON object per line. Append-only so a crash mid-record
never loses earlier steps, and human-inspectable so a user can audit exactly what
was captured before sharing it.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from types import TracebackType

SCHEMA_VERSION = 1


class StepKind(str, Enum):
    """The three things a session line can be."""

    COMMAND = "command"  # something the user ran
    NOTE = "note"  # a human annotation (`# ...` while recording)
    SECTION = "section"  # a heading that groups following steps (`## ...`)


@dataclass
class Step:
    """A single recorded event in a session.

    ``output`` may be truncated at capture time; it is never relied upon for
    re-running (only ``text`` is). ``redacted`` is set by the build step, not here.
    """

    index: int
    kind: StepKind
    text: str
    cwd: str | None = None
    exit_code: int | None = None
    started_at: str | None = None  # ISO-8601 local timestamp
    duration_ms: int | None = None
    output: str | None = None
    redacted: bool = False

    def to_dict(self) -> dict[str, object]:
        d = asdict(self)
        d["kind"] = self.kind.value
        return d

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> Step:
        return cls(
            index=_req_int(raw["index"]),
            kind=StepKind(str(raw["kind"])),
            text=str(raw["text"]),
            cwd=_opt_str(raw.get("cwd")),
            exit_code=_opt_int(raw.get("exit_code")),
            started_at=_opt_str(raw.get("started_at")),
            duration_ms=_opt_int(raw.get("duration_ms")),
            output=_opt_str(raw.get("output")),
            redacted=bool(raw.get("redacted", False)),
        )


def _opt_str(value: object) -> str | None:
    return None if value is None else str(value)


def _req_int(value: object) -> int:
    return value if isinstance(value, int) else int(str(value))


def _opt_int(value: object) -> int | None:
    return None if value is None else _req_int(value)


class SessionWriter:
    """Append :class:`Step` objects to a JSONL file as they happen.

    Used as a context manager during ``runscribe record`` so each step is flushed to
    disk immediately — if the terminal dies, everything up to that point survives.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self.path.open("a", encoding="utf-8")

    def append(self, step: Step) -> None:
        self._fh.write(json.dumps(step.to_dict(), ensure_ascii=False) + "\n")
        self._fh.flush()

    def close(self) -> None:
        if not self._fh.closed:
            self._fh.close()

    def __enter__(self) -> SessionWriter:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()


def read_session(path: Path) -> list[Step]:
    """Load every step from a session JSONL file, skipping blank lines."""
    steps: list[Step] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        steps.append(Step.from_dict(json.loads(line)))
    return steps

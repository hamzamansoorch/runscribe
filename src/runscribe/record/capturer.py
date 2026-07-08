"""The capture abstraction.

Implementations: :class:`~runscribe.record.subprocess_capturer.SubprocessCapturer`
(M1, per-command, cross-platform) and
:class:`~runscribe.record.persistent_capturer.PersistentShellCapturer` (M2, one
long-lived POSIX shell so state persists). Everything else in runscribe depends
only on this interface, so swapping capturers touches nothing else.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class CommandResult:
    """The outcome of running one command."""

    output: str
    exit_code: int
    duration_ms: int
    cwd: str


class Capturer(ABC):
    """Runs commands and reports their result, tracking working directory state."""

    @property
    @abstractmethod
    def cwd(self) -> str:
        """The current working directory the next command will run in."""

    @abstractmethod
    def run(self, command: str) -> CommandResult:
        """Execute ``command`` and return its captured result."""

    def close(self) -> None:  # noqa: B027 - optional hook; most capturers need no cleanup
        """Release any resources (e.g. a long-lived shell). Default: no-op."""

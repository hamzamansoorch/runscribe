"""Session capture."""

from __future__ import annotations

import sys

from .capturer import Capturer, CommandResult
from .persistent_capturer import (
    PersistentShellCapturer,
    PersistentShellError,
    default_posix_shell,
)
from .pty_capturer import PtyCapturer, pty_supported
from .subprocess_capturer import SubprocessCapturer

__all__ = [
    "Capturer",
    "CommandResult",
    "PersistentShellCapturer",
    "PersistentShellError",
    "PtyCapturer",
    "SubprocessCapturer",
    "make_capturer",
    "pty_supported",
]


def make_capturer(*, persistent: bool | None = None, pty: bool = False) -> Capturer:
    """Pick a capturer.

    - ``pty=True``: highest-fidelity PTY capturer (POSIX only; raises if
      unavailable so the caller can fall back).
    - ``persistent=True``: the persistent POSIX shell (state carries across
      steps); ``False``: the per-command subprocess capturer.
    - ``persistent=None`` (default): persistent shell on POSIX when a shell is
      available, else the subprocess capturer.
    """
    if pty:
        return PtyCapturer()
    if persistent is False:
        return SubprocessCapturer()
    if persistent is True:
        return PersistentShellCapturer()
    if sys.platform != "win32" and default_posix_shell() is not None:
        return PersistentShellCapturer()
    return SubprocessCapturer()

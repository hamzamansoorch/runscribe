"""Session capture."""

from __future__ import annotations

import sys

from .capturer import Capturer, CommandResult
from .persistent_capturer import (
    PersistentShellCapturer,
    PersistentShellError,
    default_posix_shell,
)
from .subprocess_capturer import SubprocessCapturer

__all__ = [
    "Capturer",
    "CommandResult",
    "PersistentShellCapturer",
    "PersistentShellError",
    "SubprocessCapturer",
    "make_capturer",
]


def make_capturer(*, persistent: bool | None = None) -> Capturer:
    """Pick the best capturer for this platform.

    ``persistent`` forces the choice: ``True`` demands the persistent POSIX
    shell (raising if unavailable), ``False`` forces the per-command subprocess
    capturer. ``None`` (default) uses the persistent shell when a POSIX shell is
    available and we're not on Windows, else falls back to the subprocess
    capturer. State (``cd``/``export``/variables) persists only with the former.
    """
    if persistent is False:
        return SubprocessCapturer()
    if persistent is True:
        return PersistentShellCapturer()
    if sys.platform != "win32" and default_posix_shell() is not None:
        return PersistentShellCapturer()
    return SubprocessCapturer()

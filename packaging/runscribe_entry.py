"""PyInstaller entry point.

PyInstaller needs a real script as the frozen program's start point; this simply
invokes the Typer app, equivalent to the `runscribe` console script.
"""

from __future__ import annotations

from runscribe.cli import app

if __name__ == "__main__":
    app()

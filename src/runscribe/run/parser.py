"""Parse a built runbook back into ordered, runnable steps.

Only fenced code blocks tagged with the ``<!-- runscribe: id=N -->`` marker are
treated as runnable — prose, section headings, and any *other* fenced blocks
(e.g. example output a user pasted in) are ignored, so ``run`` never executes
something that was only meant to be read. The nearest preceding ``## `` heading
is attached to each step for display context.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_MARKER_RE = re.compile(r"<!--\s*runscribe:\s*id=(\d+)\s*-->")
_FENCE = "```"


@dataclass
class ParsedStep:
    id: int
    command: str
    section: str | None = None


def parse_runbook(markdown: str) -> list[ParsedStep]:
    """Extract the runnable command steps from a runbook's Markdown."""
    lines = markdown.splitlines()
    steps: list[ParsedStep] = []
    section: str | None = None
    i = 0
    n = len(lines)

    while i < n:
        stripped = lines[i].strip()

        if stripped.startswith("## "):
            section = stripped[3:].strip()
            i += 1
            continue

        marker = _MARKER_RE.search(stripped)
        if not marker:
            i += 1
            continue

        # Find the opening fence that should follow the marker, but bail if we
        # hit another marker or a heading first (a marker without a code block).
        fence = i + 1
        while fence < n and not lines[fence].lstrip().startswith(_FENCE):
            if _MARKER_RE.search(lines[fence]) or lines[fence].strip().startswith("#"):
                break
            fence += 1

        if fence >= n or not lines[fence].lstrip().startswith(_FENCE):
            i += 1
            continue

        body: list[str] = []
        close = fence + 1
        while close < n and not lines[close].lstrip().startswith(_FENCE):
            body.append(lines[close])
            close += 1

        command = "\n".join(body).strip("\n")
        if command:
            steps.append(ParsedStep(id=int(marker.group(1)), command=command, section=section))
        i = close + 1

    return steps

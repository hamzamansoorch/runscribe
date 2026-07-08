"""``{{PLACEHOLDER}}`` discovery and substitution for runbook commands.

A runbook can parameterise commands with ``{{NAME}}`` tokens (e.g.
``kubectl config use-context {{CLUSTER}}``). ``run`` collects the distinct
names, resolves a value for each once, and substitutes them at execution time.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

# Names are conservative identifiers so we never mistake shell braces like
# ${VAR} or brace-expansion {a,b} for a runscribe placeholder.
_PLACEHOLDER_RE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")


def find_placeholders(texts: Iterable[str]) -> list[str]:
    """Return the distinct placeholder names across ``texts``, in first-seen order."""
    seen: dict[str, None] = {}
    for text in texts:
        for match in _PLACEHOLDER_RE.finditer(text):
            seen.setdefault(match.group(1), None)
    return list(seen)


def substitute(text: str, values: Mapping[str, str]) -> str:
    """Replace ``{{NAME}}`` with ``values[NAME]``; leave unknown names untouched."""
    return _PLACEHOLDER_RE.sub(
        lambda m: values.get(m.group(1), m.group(0)),
        text,
    )

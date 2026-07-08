"""Load a user's ``.runscribe/redact.toml`` and build a configured Redactor.

Example ``.runscribe/redact.toml``::

    # Extra regexes to scrub (matched spans are replaced with <REDACTED>).
    patterns = ["INTERNAL-[0-9]{6}", "acme-[a-z]+-key"]

    # Exact strings to always scrub (escaped for you — no regex needed).
    literals = ["super-secret-codename", "10.0.0.42"]

Missing file → built-in rules only. Malformed file → :class:`RedactConfigError`.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # Python 3.10 gets the tomli backport (declared as a conditional dependency).
    import tomli as tomllib

from .rules import Redactor

DEFAULT_CONFIG_PATH = Path(".runscribe") / "redact.toml"


class RedactConfigError(Exception):
    """The redaction config exists but is invalid."""


def load_redactor(config_path: Path | None = None) -> Redactor:
    """Build a :class:`Redactor` from built-ins plus the config file, if present.

    ``config_path`` defaults to ``.runscribe/redact.toml`` in the current
    directory. A missing file is fine — you get the built-in rules.
    """
    path = config_path or DEFAULT_CONFIG_PATH
    if not path.exists():
        return Redactor.with_defaults()

    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError) as exc:
        raise RedactConfigError(f"could not read {path}: {exc}") from exc

    patterns = _string_list(data.get("patterns", []), path, "patterns")
    literals = _string_list(data.get("literals", []), path, "literals")

    for pattern in patterns:
        try:
            re.compile(pattern)
        except re.error as exc:
            raise RedactConfigError(f"invalid regex in {path}: {pattern!r} ({exc})") from exc

    return Redactor.with_defaults(extra_patterns=patterns, literals=literals)


def _string_list(value: object, path: Path, key: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise RedactConfigError(f"'{key}' in {path} must be a list of strings")
    return list(value)

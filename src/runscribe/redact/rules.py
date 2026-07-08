"""Secret-redaction engine: built-in rules plus user-defined extensions.

Conservative by design: it is far better to over-redact (a placeholder where a
value was harmless) than to leak a real secret into a runbook someone shares.
This is *not* a guarantee — see the README caveat. Users extend it with a
``.runscribe/redact.toml`` (loaded by :mod:`runscribe.redact.config`).
"""

from __future__ import annotations

import re
from collections.abc import Iterable

PLACEHOLDER = "<REDACTED>"

# Each rule replaces only the sensitive span (often a capture group) so the
# surrounding command stays readable, e.g. ``export TOKEN=<REDACTED>``.
_BUILTIN_RULES: list[tuple[re.Pattern[str], str]] = [
    # PEM private key blocks — collapse the whole block.
    (
        re.compile(
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
            re.DOTALL,
        ),
        PLACEHOLDER,
    ),
    # KEY=value / KEY: value where the key name looks secret. Value runs to
    # whitespace or quote. The key name itself is preserved via the backref.
    (
        re.compile(
            r"(?i)\b([A-Z0-9_]*(?:SECRET|PASSWORD|PASSWD|TOKEN|API[_-]?KEY|ACCESS[_-]?KEY|PRIVATE[_-]?KEY|CREDENTIAL)[A-Z0-9_]*\s*[=:]\s*)"
            r"(\"[^\"]*\"|'[^']*'|[^\s]+)",
        ),
        r"\1" + PLACEHOLDER,
    ),
    # Credentials embedded in URLs: scheme://user:pass@host
    (re.compile(r"(://[^\s:/@]+:)([^\s@/]+)(@)"), r"\1" + PLACEHOLDER + r"\3"),
    # Authorization / Bearer / Basic header values.
    (re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._\-+/=]{8,}"), r"\1 " + PLACEHOLDER),
    # Well-known provider token shapes (prefix-anchored to avoid false positives).
    (re.compile(r"\bsk-[A-Za-z0-9]{16,}\b"), PLACEHOLDER),  # OpenAI-style
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"), PLACEHOLDER),  # GitHub tokens
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"), PLACEHOLDER),  # Slack tokens
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), PLACEHOLDER),  # AWS access key id
    (re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"), PLACEHOLDER),  # Google API key
    (
        re.compile(r"\bghs_[A-Za-z0-9]{20,}\b|\beyJ[A-Za-z0-9._\-]{20,}\b"),
        PLACEHOLDER,
    ),  # JWTs
]


class Redactor:
    """Applies an ordered list of ``(pattern, replacement)`` rules to text."""

    def __init__(self, rules: list[tuple[re.Pattern[str], str]]) -> None:
        self._rules = rules

    def redact(self, text: str) -> tuple[str, bool]:
        """Return ``(redacted_text, changed)``.

        ``changed`` is ``True`` if any rule matched, letting callers flag a step
        so the UI can warn the user that something was scrubbed.
        """
        if not text:
            return text, False
        result = text
        for pattern, repl in self._rules:
            result = pattern.sub(repl, result)
        return result, result != text

    @classmethod
    def with_defaults(
        cls,
        *,
        extra_patterns: Iterable[str] = (),
        literals: Iterable[str] = (),
    ) -> Redactor:
        """Build a redactor from the built-in rules plus user extensions.

        ``extra_patterns`` are regexes; ``literals`` are exact strings (escaped).
        Both are appended after the built-ins and replaced with the placeholder.
        """
        rules = list(_BUILTIN_RULES)
        for literal in literals:
            if literal:
                rules.append((re.compile(re.escape(literal)), PLACEHOLDER))
        for pattern in extra_patterns:
            if pattern:
                rules.append((re.compile(pattern), PLACEHOLDER))
        return cls(rules)


_DEFAULT = Redactor.with_defaults()


def redact(text: str) -> tuple[str, bool]:
    """Redact using only the built-in rules (no user config)."""
    return _DEFAULT.redact(text)

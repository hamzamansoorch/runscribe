"""Redaction must scrub secrets while leaving ordinary commands intact."""

from __future__ import annotations

import pytest

from runscribe.redact import redact

_SECRETS = [
    "export API_KEY=sk-abcdef0123456789abcdef",
    'DATABASE_PASSWORD="hunter2-very-secret"',
    "curl -H 'Authorization: Bearer abcdef123456789xyz' https://api.example.com",
    "git clone https://user:s3cr3tpass@github.com/org/repo.git",
    "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ012345",
    "AKIAIOSFODNN7EXAMPLE",
]


@pytest.mark.parametrize("text", _SECRETS)
def test_secrets_are_redacted(text: str) -> None:
    cleaned, changed = redact(text)
    assert changed is True
    assert "<REDACTED>" in cleaned
    # None of the raw secret material should survive.
    for leaked in ("sk-abcdef", "hunter2", "s3cr3tpass", "ghp_ABCDEF", "AKIAIOSFODNN7EXAMPLE"):
        assert leaked not in cleaned


def test_key_name_is_preserved() -> None:
    cleaned, _ = redact("export API_KEY=sk-abcdef0123456789abcdef")
    assert cleaned.startswith("export API_KEY=")


@pytest.mark.parametrize(
    "text",
    [
        "git status",
        "docker compose up -d",
        "cd /var/www && ls -la",
        "echo hello world",
    ],
)
def test_ordinary_commands_untouched(text: str) -> None:
    cleaned, changed = redact(text)
    assert changed is False
    assert cleaned == text


def test_empty_string() -> None:
    assert redact("") == ("", False)

"""User-extensible redaction via .runscribe/redact.toml."""

from __future__ import annotations

from pathlib import Path

import pytest

from runscribe.redact import RedactConfigError, load_redactor


def test_missing_config_uses_builtins_only(tmp_path: Path) -> None:
    redactor = load_redactor(tmp_path / "redact.toml")
    # Built-in rule still fires...
    assert redactor.redact("token sk-abcdef0123456789abcdef")[1] is True
    # ...but a custom internal id is left alone without config.
    assert redactor.redact("ticket INTERNAL-123456")[1] is False


def test_custom_patterns_and_literals(tmp_path: Path) -> None:
    cfg = tmp_path / "redact.toml"
    cfg.write_text(
        'patterns = ["INTERNAL-[0-9]{6}"]\nliterals = ["project-bluebird"]\n',
        encoding="utf-8",
    )
    redactor = load_redactor(cfg)

    cleaned_pattern, changed_pattern = redactor.redact("see INTERNAL-123456 for details")
    assert changed_pattern is True
    assert "INTERNAL-123456" not in cleaned_pattern

    cleaned_literal, changed_literal = redactor.redact("codename project-bluebird ships friday")
    assert changed_literal is True
    assert "project-bluebird" not in cleaned_literal


def test_invalid_regex_raises(tmp_path: Path) -> None:
    cfg = tmp_path / "redact.toml"
    cfg.write_text('patterns = ["([unclosed"]\n', encoding="utf-8")
    with pytest.raises(RedactConfigError):
        load_redactor(cfg)


def test_wrong_type_raises(tmp_path: Path) -> None:
    cfg = tmp_path / "redact.toml"
    cfg.write_text('patterns = "not-a-list"\n', encoding="utf-8")
    with pytest.raises(RedactConfigError):
        load_redactor(cfg)

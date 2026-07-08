"""HTML export renders a self-contained, escaped page."""

from __future__ import annotations

from runscribe.build import build_runbook, render_html
from runscribe.session import Step, StepKind


def test_html_structure_and_escaping() -> None:
    steps = [
        Step(index=0, kind=StepKind.SECTION, text="Deploy <prod>"),
        Step(index=1, kind=StepKind.NOTE, text="mind the <tag> & spaces"),
        Step(index=2, kind=StepKind.COMMAND, text="echo 'a' && grep <x>", exit_code=0),
        Step(index=3, kind=StepKind.COMMAND, text="false", exit_code=2),
    ]
    html = render_html(build_runbook(steps, title="My & Runbook", created="2026-07-08"))

    assert html.startswith("<!doctype html>")
    assert "<style>" in html  # CSS is inlined (self-contained)
    assert "<title>My &amp; Runbook</title>" in html
    assert "<h2>Deploy &lt;prod&gt;</h2>" in html
    assert "mind the &lt;tag&gt; &amp; spaces" in html
    assert "echo &#x27;a&#x27; &amp;&amp; grep &lt;x&gt;" in html  # command escaped, not run
    assert "exited with code 2" in html
    # No raw injection of the angle brackets from user content.
    assert "<prod>" not in html
    assert "<x>" not in html


def test_html_is_deterministic() -> None:
    steps = [Step(index=0, kind=StepKind.COMMAND, text="ls -la /srv", exit_code=0)]
    a = render_html(build_runbook(steps, title="t", created="c", drop_noise=False))
    b = render_html(build_runbook(steps, title="t", created="c", drop_noise=False))
    assert a == b

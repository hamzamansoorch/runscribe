"""Build a runbook from steps and check the rendered Markdown (golden-ish)."""

from __future__ import annotations

from runscribe.build import build_runbook, render_markdown
from runscribe.session import Step, StepKind


def _sample_steps() -> list[Step]:
    return [
        Step(index=0, kind=StepKind.SECTION, text="Deploy the API"),
        Step(index=1, kind=StepKind.NOTE, text="Make sure you're on the release tag"),
        Step(index=2, kind=StepKind.COMMAND, text="git checkout v1.4.2", exit_code=0),
        Step(index=3, kind=StepKind.COMMAND, text="ls -la", exit_code=0),  # noise
        Step(index=4, kind=StepKind.COMMAND, text="./deploy.sh staging", exit_code=0),
        Step(
            index=5,
            kind=StepKind.COMMAND,
            text="export TOKEN=sk-abcdef0123456789abcdef",
            exit_code=0,
        ),
    ]


def test_build_drops_noise_and_counts_commands() -> None:
    runbook = build_runbook(
        _sample_steps(), title="Deploy", created="2026-07-06T14:00:00"
    )
    texts = [s.text for s in runbook.steps]
    assert "ls -la" not in texts  # noise dropped
    assert runbook.command_count == 3
    assert runbook.redacted_count == 1


def test_keep_noise_flag() -> None:
    runbook = build_runbook(
        _sample_steps(), title="Deploy", created="x", drop_noise=False
    )
    assert runbook.command_count == 4


def test_render_markdown_golden() -> None:
    runbook = build_runbook(
        _sample_steps(), title="Deploy", created="2026-07-06T14:00:00"
    )
    md = render_markdown(runbook)
    expected = """\
---
title: Deploy
created: "2026-07-06T14:00:00"
generated_by: runscribe
---

# Deploy

## Deploy the API

Make sure you're on the release tag

<!-- runscribe: id=1 -->
```bash
git checkout v1.4.2
```

<!-- runscribe: id=2 -->
```bash
./deploy.sh staging
```

<!-- runscribe: id=3 -->
```bash
export TOKEN=<REDACTED>
```

> **Note:** a secret was redacted from this step.
"""
    assert md == expected


def test_nonzero_exit_is_annotated() -> None:
    steps = [Step(index=0, kind=StepKind.COMMAND, text="false", exit_code=1)]
    md = render_markdown(build_runbook(steps, title="t", created="c"))
    assert "exited with code 1" in md


def test_consecutive_duplicate_commands_collapse() -> None:
    steps = [
        Step(index=0, kind=StepKind.COMMAND, text="./deploy.sh", exit_code=1),
        Step(index=1, kind=StepKind.COMMAND, text="./deploy.sh", exit_code=0),  # re-run
    ]
    runbook = build_runbook(steps, title="t", created="c")
    assert runbook.command_count == 1


def test_duplicate_not_collapsed_across_a_note() -> None:
    steps = [
        Step(index=0, kind=StepKind.COMMAND, text="make build"),
        Step(index=1, kind=StepKind.NOTE, text="now again after fixing config"),
        Step(index=2, kind=StepKind.COMMAND, text="make build"),
    ]
    runbook = build_runbook(steps, title="t", created="c")
    assert runbook.command_count == 2


def test_dir_is_treated_as_noise() -> None:
    steps = [Step(index=0, kind=StepKind.COMMAND, text="dir", exit_code=0)]
    assert build_runbook(steps, title="t", created="c").command_count == 0

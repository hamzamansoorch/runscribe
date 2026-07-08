"""Render a :class:`~runscribe.build.builder.Runbook` to Markdown.

The output is intentionally plain Markdown a human can hand-edit. Command steps
carry an ``<!-- runscribe: id=N -->`` marker so the M3 ``run`` command can find and
re-execute exactly the runnable steps without a proprietary file format and
without mistaking prose or example output for something to execute.
"""

from __future__ import annotations

from ..session import StepKind
from .builder import Runbook, RunbookStep

_GENERATED_BY = "runscribe"


def render_markdown(runbook: Runbook) -> str:
    lines: list[str] = []
    lines.extend(_front_matter(runbook))
    lines.append("")
    lines.append(f"# {runbook.title}")
    lines.append("")

    command_id = 0
    for step in runbook.steps:
        if step.kind is StepKind.SECTION:
            lines.append(f"## {step.text.strip()}")
            lines.append("")
        elif step.kind is StepKind.NOTE:
            lines.append(step.text.strip())
            lines.append("")
        elif step.kind is StepKind.COMMAND:
            command_id += 1
            lines.extend(_render_command(step, command_id))
            lines.append("")

    return "\n".join(lines).rstrip("\n") + "\n"


def _front_matter(runbook: Runbook) -> list[str]:
    fm = [
        "---",
        f"title: {_yaml_scalar(runbook.title)}",
        f"created: {_yaml_scalar(runbook.created)}",
        f"generated_by: {_GENERATED_BY}",
        "---",
    ]
    return fm


def _render_command(step: RunbookStep, command_id: int) -> list[str]:
    block = [
        f"<!-- runscribe: id={command_id} -->",
        "```bash",
        step.text.rstrip("\n"),
        "```",
    ]
    annotations = []
    if step.exit_code not in (None, 0):
        annotations.append(
            f"> **Warning:** this command exited with code {step.exit_code} when recorded."
        )
    if step.redacted:
        annotations.append("> **Note:** a secret was redacted from this step.")
    if annotations:
        block.append("")
        block.extend(annotations)
    return block


def _yaml_scalar(value: str) -> str:
    """Quote a scalar if it could confuse a YAML parser; otherwise leave it bare."""
    if value == "" or value[0] in "!&*[]{}#|>@`\"'%," or ":" in value or value != value.strip():
        escaped = value.replace('"', '\\"')
        return f'"{escaped}"'
    return value

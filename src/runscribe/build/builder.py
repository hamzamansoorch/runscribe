"""Transform a raw recorded session into a cleaned :class:`Runbook` model.

The builder is where "what actually happened" becomes "what someone should do":
it redacts secrets, drops obvious noise, and carries just enough metadata for the
M3 ``run`` command to re-execute command steps. Rendering to text lives in
:mod:`runscribe.build.markdown`; this module stays presentation-free.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..redact import Redactor
from ..session import Step, StepKind

# Commands too trivial to belong in an SOP on their own. They're navigation and
# inspection, not procedure. Kept out of the runbook but never out of the raw
# session file. Deliberately conservative — better to keep a step than to drop a
# meaningful one.
DEFAULT_NOISE_COMMANDS = frozenset(
    {"ls", "ll", "la", "dir", "pwd", "clear", "cls", "history"}
)


@dataclass
class RunbookStep:
    kind: StepKind
    text: str
    exit_code: int | None = None
    redacted: bool = False


@dataclass
class Runbook:
    title: str
    created: str
    steps: list[RunbookStep] = field(default_factory=list)

    @property
    def command_count(self) -> int:
        return sum(1 for s in self.steps if s.kind is StepKind.COMMAND)

    @property
    def redacted_count(self) -> int:
        return sum(1 for s in self.steps if s.redacted)


def build_runbook(
    steps: list[Step],
    *,
    title: str,
    created: str,
    drop_noise: bool = True,
    redactor: Redactor | None = None,
    noise_commands: frozenset[str] = DEFAULT_NOISE_COMMANDS,
) -> Runbook:
    """Build a :class:`Runbook` from raw session steps.

    ``created`` is passed in (rather than read from a clock) so builds are
    deterministic and golden-file testable. ``redactor`` defaults to the
    built-in ruleset; pass a configured one to honour ``.runscribe/redact.toml``.
    """
    redactor = redactor or Redactor.with_defaults()
    runbook = Runbook(title=title, created=created)

    # Track the previous *command* text so an immediately-repeated command (a
    # re-run of the same line) collapses to one step. Reset by any note/section,
    # since a command repeated after a comment is likely intentional.
    prev_command: str | None = None

    for step in steps:
        if step.kind is StepKind.COMMAND:
            normalized = step.text.strip()
            if drop_noise and _is_noise(normalized, noise_commands):
                continue
            if normalized == prev_command:
                continue
            prev_command = normalized
        else:
            prev_command = None

        clean_text, changed = redactor.redact(step.text)
        runbook.steps.append(
            RunbookStep(
                kind=step.kind,
                text=clean_text,
                exit_code=step.exit_code,
                redacted=changed,
            )
        )
    return runbook


def _is_noise(command: str, noise_commands: frozenset[str]) -> bool:
    head = command.split()
    return bool(head) and head[0] in noise_commands

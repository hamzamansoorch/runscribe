"""Execute a parsed runbook step by step.

The orchestration is deliberately I/O-free: confirmation and output display are
injected as callbacks, so the loop is unit-testable with fakes and the CLI owns
all the actual prompting/printing. Commands run through a
:class:`~runscribe.record.Capturer`; on POSIX that is the persistent shell, so
``cd``/``export`` in one step carry into the next exactly like the original
session.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import Enum

from ..record import Capturer
from .params import substitute
from .parser import ParsedStep


class Decision(str, Enum):
    RUN = "run"
    SKIP = "skip"
    QUIT = "quit"


class Status(str, Enum):
    RAN = "ran"  # executed, exit code 0
    FAILED = "failed"  # executed, non-zero exit
    SKIPPED = "skipped"  # user chose to skip


@dataclass
class StepOutcome:
    step: ParsedStep
    command: str  # after placeholder substitution
    status: Status
    exit_code: int | None
    output: str


@dataclass
class RunReport:
    outcomes: list[StepOutcome] = field(default_factory=list)
    stopped_early: bool = False  # a failure (or quit-after) ended the run

    @property
    def ran(self) -> int:
        return sum(1 for o in self.outcomes if o.status is Status.RAN)

    @property
    def failed(self) -> int:
        return sum(1 for o in self.outcomes if o.status is Status.FAILED)

    @property
    def skipped(self) -> int:
        return sum(1 for o in self.outcomes if o.status is Status.SKIPPED)

    @property
    def ok(self) -> bool:
        return self.failed == 0 and not self.stopped_early


# confirm(step, resolved_command) -> Decision
Confirm = Callable[[ParsedStep, str], Decision]
# on_output(step, result_output) -> None
OnOutput = Callable[[ParsedStep, str], None]


def run_runbook(
    steps: list[ParsedStep],
    capturer: Capturer,
    *,
    values: Mapping[str, str],
    confirm: Confirm,
    on_output: OnOutput,
    keep_going: bool = False,
) -> RunReport:
    """Run ``steps`` in order, asking ``confirm`` before each.

    Stops after the first failing step unless ``keep_going`` is set. Choosing
    :attr:`Decision.QUIT` ends the run immediately (not counted as a failure).
    """
    report = RunReport()
    for step in steps:
        command = substitute(step.command, values)

        decision = confirm(step, command)
        if decision is Decision.QUIT:
            report.stopped_early = True
            break
        if decision is Decision.SKIP:
            report.outcomes.append(
                StepOutcome(step, command, Status.SKIPPED, exit_code=None, output="")
            )
            continue

        result = capturer.run(command)
        on_output(step, result.output)
        status = Status.RAN if result.exit_code == 0 else Status.FAILED
        report.outcomes.append(
            StepOutcome(step, command, status, result.exit_code, result.output)
        )
        if status is Status.FAILED and not keep_going:
            report.stopped_early = True
            break

    return report

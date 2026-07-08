"""Parser, placeholder handling, and the step runner for `runscribe run`."""

from __future__ import annotations

from runscribe.build import build_runbook, render_markdown
from runscribe.record.capturer import Capturer, CommandResult
from runscribe.run import (
    Decision,
    ParsedStep,
    find_placeholders,
    parse_runbook,
    run_runbook,
    substitute,
)
from runscribe.session import Step, StepKind

# --- parser -------------------------------------------------------------


def test_parser_extracts_only_marked_blocks() -> None:
    md = """\
# Title

## Setup

Some prose, and an example block that must NOT run:

```bash
rm -rf /   # scary example, not tagged
```

<!-- runscribe: id=1 -->
```bash
echo hello
```
"""
    steps = parse_runbook(md)
    assert len(steps) == 1
    assert steps[0].command == "echo hello"
    assert steps[0].section == "Setup"


def test_parser_multiple_steps_track_sections() -> None:
    md = """\
## First
<!-- runscribe: id=1 -->
```bash
one
```
## Second
<!-- runscribe: id=2 -->
```sh
two
```
"""
    steps = parse_runbook(md)
    assert [(s.command, s.section) for s in steps] == [("one", "First"), ("two", "Second")]


def test_parser_marker_without_block_is_skipped() -> None:
    md = "<!-- runscribe: id=1 -->\n\n## Next section\n"
    assert parse_runbook(md) == []


# --- placeholders -------------------------------------------------------


def test_find_placeholders_dedup_in_order() -> None:
    cmds = ["deploy {{ENV}} {{REGION}}", "check {{ENV}}"]
    assert find_placeholders(cmds) == ["ENV", "REGION"]


def test_substitute_replaces_known_leaves_unknown() -> None:
    assert substitute("scale {{APP}} in {{ENV}}", {"APP": "web"}) == "scale web in {{ENV}}"


# --- runner -------------------------------------------------------------


class FakeCapturer(Capturer):
    def __init__(self, fail_on: set[str] | None = None) -> None:
        self._fail = fail_on or set()
        self.ran: list[str] = []

    @property
    def cwd(self) -> str:
        return "/fake"

    def run(self, command: str) -> CommandResult:
        self.ran.append(command)
        code = 1 if command in self._fail else 0
        return CommandResult(output=f"out:{command}", exit_code=code, duration_ms=1, cwd="/fake")


def _steps(*commands: str) -> list[ParsedStep]:
    return [ParsedStep(id=i, command=c) for i, c in enumerate(commands, 1)]


def _always(decision: Decision):  # type: ignore[no-untyped-def]
    return lambda _step, _cmd: decision


def _noop_output(_step: ParsedStep, _output: str) -> None:
    return None


def test_runner_runs_all_steps_with_substitution() -> None:
    cap = FakeCapturer()
    report = run_runbook(
        _steps("echo {{WHO}}", "pwd"),
        cap,
        values={"WHO": "world"},
        confirm=_always(Decision.RUN),
        on_output=_noop_output,
    )
    assert cap.ran == ["echo world", "pwd"]
    assert report.ran == 2
    assert report.ok is True


def test_runner_halts_on_failure() -> None:
    cap = FakeCapturer(fail_on={"boom"})
    report = run_runbook(
        _steps("ok", "boom", "after"),
        cap,
        values={},
        confirm=_always(Decision.RUN),
        on_output=_noop_output,
    )
    assert cap.ran == ["ok", "boom"]  # third never runs
    assert report.stopped_early is True
    assert report.failed == 1
    assert report.ok is False


def test_runner_keep_going_continues_past_failure() -> None:
    cap = FakeCapturer(fail_on={"boom"})
    report = run_runbook(
        _steps("boom", "after"),
        cap,
        values={},
        confirm=_always(Decision.RUN),
        on_output=_noop_output,
        keep_going=True,
    )
    assert cap.ran == ["boom", "after"]
    assert report.failed == 1
    assert report.ok is False  # a failure still means "not clean"


def test_runner_skip_and_quit() -> None:
    cap = FakeCapturer()

    def confirm(step: ParsedStep, _cmd: str) -> Decision:
        return {1: Decision.SKIP, 2: Decision.RUN, 3: Decision.QUIT}[step.id]

    report = run_runbook(
        _steps("a", "b", "c"), cap, values={}, confirm=confirm, on_output=_noop_output
    )
    assert cap.ran == ["b"]  # a skipped, c quit-before-run
    assert report.skipped == 1
    assert report.ran == 1
    assert report.stopped_early is True


# --- pipeline round-trip ------------------------------------------------


def test_build_then_parse_roundtrip() -> None:
    session = [
        Step(index=0, kind=StepKind.SECTION, text="Deploy"),
        Step(index=1, kind=StepKind.COMMAND, text="./deploy.sh {{ENV}}", exit_code=0),
        Step(index=2, kind=StepKind.COMMAND, text="ls", exit_code=0),  # noise, dropped
        Step(index=3, kind=StepKind.COMMAND, text="curl https://health/{{ENV}}", exit_code=0),
    ]
    md = render_markdown(build_runbook(session, title="Deploy", created="c"))
    parsed = parse_runbook(md)
    assert [s.command for s in parsed] == ["./deploy.sh {{ENV}}", "curl https://health/{{ENV}}"]
    assert parsed[0].section == "Deploy"
    assert find_placeholders(s.command for s in parsed) == ["ENV"]

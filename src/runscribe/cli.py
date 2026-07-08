"""Command-line entry point for runscribe.

Two verbs ship in M1: ``record`` (capture a session to JSONL) and ``build``
(turn that JSONL into a Markdown runbook). ``run`` arrives in M3.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import typer
from rich.console import Console

from . import __version__
from .build import build_runbook, render_html, render_markdown
from .record import Capturer, PersistentShellError, make_capturer
from .redact import RedactConfigError, load_redactor
from .run import Decision, ParsedStep, find_placeholders, parse_runbook, run_runbook
from .session import SessionWriter, Step, StepKind, read_session

# Ensure captured output and rendered runbooks (which may contain non-ASCII) never
# crash on a legacy Windows console still defaulting to cp1252.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except (AttributeError, ValueError):  # pragma: no cover - non-reconfigurable stream
        pass

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="runscribe — capture what you did in the terminal into a re-runnable runbook. "
    "100% local: your history never leaves your machine, and there is no AI.",
    context_settings={"help_option_names": ["-h", "--help"]},
)

_DEFAULT_SESSION_DIR = Path(".runscribe") / "sessions"
_console = Console()
_err = Console(stderr=True)


def _version_callback(value: bool) -> None:
    if value:
        _console.print(f"runscribe {__version__}")
        raise typer.Exit()


@app.callback()
def _main(
    _version: bool = typer.Option(
        False, "-V", "--version", callback=_version_callback, is_eager=True,
        help="Show the version and exit.",
    ),
) -> None:
    """runscribe — the terminal-to-runbook recorder."""


@app.command()
def record(
    out_dir: Path = typer.Option(
        _DEFAULT_SESSION_DIR, "--out-dir", help="Where to write the session file."
    ),
    subprocess_only: bool = typer.Option(
        False,
        "--subprocess",
        help="Run each command in its own process (no cd/export state carried over).",
    ),
    persistent: bool = typer.Option(
        False,
        "--persistent",
        help="Force one long-lived POSIX shell so cd/export/vars persist (needs bash/sh).",
    ),
) -> None:
    """Start recording. Type commands normally.

    Prefix a line with '# ' to add a note, or '## ' to start a new section.
    Type 'exit' (or press Ctrl-D) to finish.
    """
    if subprocess_only and persistent:
        _err.print("[red]X[/red] --subprocess and --persistent are mutually exclusive")
        raise typer.Exit(2)

    out_dir.mkdir(parents=True, exist_ok=True)
    session_path = out_dir / f"{datetime.now():%Y%m%d-%H%M%S}.jsonl"

    capturer = _make_capturer(subprocess_only=subprocess_only, persistent=persistent)

    _console.print("[bold green]* recording[/bold green] - "
                   "commands run for real; [cyan]# note[/cyan], [cyan]## section[/cyan], "
                   "[cyan]exit[/cyan] to finish.")
    _console.print(f"[dim]session: {session_path}[/dim]\n")

    index = 0
    commands = 0
    try:
        with SessionWriter(session_path) as writer:
            while True:
                try:
                    line = input(f"runscribe:{_short_cwd(capturer.cwd)}$ ")
                except EOFError:
                    _console.print()
                    break
                except KeyboardInterrupt:
                    _console.print("\n[dim](Ctrl-C — type 'exit' to finish)[/dim]")
                    continue

                # Strip a leading BOM that some shells prepend when piping input.
                stripped = line.lstrip(chr(0xFEFF)).strip()
                if stripped in ("exit", "quit"):
                    break
                if not stripped:
                    continue

                try:
                    step = _line_to_step(stripped, index, capturer)
                except PersistentShellError as exc:
                    _err.print(f"[red]X[/red] shell error: {exc}")
                    break
                writer.append(step)
                index += 1
                if step.kind is StepKind.COMMAND:
                    commands += 1
                    if step.output:
                        print(step.output)  # plain print: never treat output as rich markup
    finally:
        capturer.close()

    _console.print(
        f"\n[bold]recorded[/bold] {commands} command(s) -> [cyan]{session_path}[/cyan]"
    )
    _console.print(f"[dim]next: runscribe build {session_path} -o runbook.md[/dim]")


def _make_capturer(*, subprocess_only: bool, persistent: bool) -> Capturer:
    if subprocess_only:
        return make_capturer(persistent=False)
    try:
        return make_capturer(persistent=True if persistent else None)
    except PersistentShellError:
        # Never block recording on shell startup — fall back transparently.
        _err.print("[yellow]![/yellow] persistent shell unavailable; using per-command capture.")
        return make_capturer(persistent=False)


def _line_to_step(line: str, index: int, capturer: Capturer) -> Step:
    now = datetime.now().isoformat(timespec="seconds")
    if line.startswith("## "):
        return Step(index=index, kind=StepKind.SECTION, text=line[3:].strip(), started_at=now)
    if line.startswith("# "):
        return Step(index=index, kind=StepKind.NOTE, text=line[2:].strip(), started_at=now)
    result = capturer.run(line)
    return Step(
        index=index,
        kind=StepKind.COMMAND,
        text=line,
        cwd=result.cwd,
        exit_code=result.exit_code,
        started_at=now,
        duration_ms=result.duration_ms,
        output=result.output or None,
    )


@app.command()
def build(
    session: Path | None = typer.Argument(
        None, help="Session .jsonl file. Omit with --last to use the newest one."
    ),
    out: Path | None = typer.Option(
        None, "-o", "--out", help="Write the runbook here (default: print to stdout)."
    ),
    title: str | None = typer.Option(None, "--title", help="Runbook title."),
    last: bool = typer.Option(
        False, "--last", help="Use the most recent session in .runscribe/sessions."
    ),
    keep_noise: bool = typer.Option(
        False, "--keep-noise", help="Keep navigation commands (ls, pwd, …)."
    ),
    redact_config: Path | None = typer.Option(
        None,
        "--redact-config",
        help="Extra redaction rules (default: .runscribe/redact.toml if present).",
    ),
    fmt: str = typer.Option(
        "md", "--format", "-f", help="Output format: 'md' (Markdown) or 'html'."
    ),
) -> None:
    """Turn a recorded session into a clean Markdown (or HTML) runbook."""
    if fmt not in ("md", "html"):
        _err.print(f"[red]X[/red] --format must be 'md' or 'html', got {fmt!r}")
        raise typer.Exit(2)
    session_path = _resolve_session(session, last)

    steps = read_session(session_path)
    if not steps:
        _err.print(f"[yellow]![/yellow] {session_path} has no steps.")
        raise typer.Exit(1)

    try:
        redactor = load_redactor(redact_config)
    except RedactConfigError as exc:
        _err.print(f"[red]X[/red] {exc}")
        raise typer.Exit(2) from exc

    runbook_title = title or _default_title(session_path)
    created = _created_from(steps, session_path)
    runbook = build_runbook(
        steps,
        title=runbook_title,
        created=created,
        drop_noise=not keep_noise,
        redactor=redactor,
    )
    rendered = render_html(runbook) if fmt == "html" else render_markdown(runbook)

    if out is None:
        print(rendered)  # plain print: rendered output must not be parsed as rich markup
    else:
        out.write_text(rendered, encoding="utf-8")
        note = f" ({runbook.redacted_count} redacted)" if runbook.redacted_count else ""
        _console.print(
            f"[bold]done[/bold] {runbook.command_count} command(s){note} -> [cyan]{out}[/cyan]"
        )


@app.command()
def run(
    runbook: Path = typer.Argument(..., help="A runbook .md produced by `runscribe build`."),
    set_values: list[str] = typer.Option(
        [], "--set", "-s", metavar="NAME=VALUE", help="Provide a {{placeholder}} value."
    ),
    assume_yes: bool = typer.Option(
        False, "--yes", "-y", help="Run every step without asking for confirmation."
    ),
    keep_going: bool = typer.Option(
        False, "--keep-going", help="Continue after a step fails instead of stopping."
    ),
    subprocess_only: bool = typer.Option(
        False, "--subprocess", help="Run each step in its own process (no state carried over)."
    ),
    persistent: bool = typer.Option(
        False, "--persistent", help="Force one long-lived POSIX shell so state persists (bash/sh)."
    ),
) -> None:
    """Re-execute a runbook step by step, with confirmations and {{placeholders}}."""
    if subprocess_only and persistent:
        _err.print("[red]X[/red] --subprocess and --persistent are mutually exclusive")
        raise typer.Exit(2)
    if not runbook.exists():
        _err.print(f"[red]X[/red] runbook not found: {runbook}")
        raise typer.Exit(2)

    steps = parse_runbook(runbook.read_text(encoding="utf-8"))
    if not steps:
        _err.print(f"[yellow]![/yellow] no runnable steps found in {runbook}")
        raise typer.Exit(1)

    try:
        values = _resolve_params(steps, set_values, assume_yes)
    except _MissingParam as exc:
        _err.print(f"[red]X[/red] {exc}")
        raise typer.Exit(2) from exc

    capturer = _make_capturer(subprocess_only=subprocess_only, persistent=persistent)
    _console.print(f"[bold]running[/bold] {len(steps)} step(s) from [cyan]{runbook}[/cyan]\n")

    last_section: str | None = None

    def confirm(step: ParsedStep, command: str) -> Decision:
        nonlocal last_section
        if step.section and step.section != last_section:
            _console.print(f"[bold]## {step.section}[/bold]")
            last_section = step.section
        _console.print(f"[cyan]$[/cyan] {command}")
        if assume_yes:
            return Decision.RUN
        while True:
            choice = input("  run this step? [Y]es / [s]kip / [q]uit: ").strip().lower()
            if choice in ("", "y", "yes"):
                return Decision.RUN
            if choice in ("s", "skip"):
                return Decision.SKIP
            if choice in ("q", "quit"):
                return Decision.QUIT

    def on_output(_step: ParsedStep, output: str) -> None:
        if output:
            print(output)  # plain print: never treat command output as rich markup

    try:
        report = run_runbook(
            steps,
            capturer,
            values=values,
            confirm=confirm,
            on_output=on_output,
            keep_going=keep_going,
        )
    finally:
        capturer.close()

    _console.print(
        f"\n[bold]done[/bold] ran {report.ran}, skipped {report.skipped}, failed {report.failed}"
    )
    if not report.ok:
        _err.print("[red]X[/red] runbook did not complete cleanly")
        raise typer.Exit(1)


class _MissingParam(Exception):
    pass


def _resolve_params(
    steps: list[ParsedStep], set_values: list[str], assume_yes: bool
) -> dict[str, str]:
    provided: dict[str, str] = {}
    for item in set_values:
        if "=" not in item:
            raise _MissingParam(f"--set expects NAME=VALUE, got {item!r}")
        name, value = item.split("=", 1)
        provided[name.strip()] = value

    values: dict[str, str] = {}
    for name in find_placeholders(step.command for step in steps):
        if name in provided:
            values[name] = provided[name]
        elif assume_yes:
            raise _MissingParam(f"missing value for {{{{{name}}}}} (pass --set {name}=...)")
        else:
            values[name] = input(f"value for {{{{{name}}}}}: ")
    return values


def _resolve_session(session: Path | None, last: bool) -> Path:
    if last:
        candidates = sorted(_DEFAULT_SESSION_DIR.glob("*.jsonl"))
        if not candidates:
            _err.print(f"[red]X[/red] no sessions found in {_DEFAULT_SESSION_DIR}")
            raise typer.Exit(2)
        return candidates[-1]
    if session is None:
        _err.print("[red]X[/red] give a session file or use --last")
        raise typer.Exit(2)
    if not session.exists():
        _err.print(f"[red]X[/red] session not found: {session}")
        raise typer.Exit(2)
    return session


def _created_from(steps: list[Step], session_path: Path) -> str:
    for step in steps:
        if step.started_at:
            return step.started_at
    return datetime.fromtimestamp(session_path.stat().st_mtime).isoformat(timespec="seconds")


def _default_title(session_path: Path) -> str:
    return f"Runbook - {session_path.stem}"


def _short_cwd(cwd: str) -> str:
    return Path(cwd).name or cwd


if __name__ == "__main__":  # pragma: no cover
    app()

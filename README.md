# runscribe

**Turn what you just did in the terminal into a clean, re-runnable runbook — offline, no AI, your history never leaves your machine.**

Every team has tribal knowledge stuck in one person's head: how to deploy, how to restore a backup, how to rotate a key. Writing it down is tedious and it goes stale the moment the commands change. `runscribe` captures a real session as you work and mechanically turns it into a plain-Markdown SOP you can edit, share, and (soon) re-run.

- 🔒 **100% local.** No account, no network, no telemetry. Nothing is ever uploaded — not to a server, not to an LLM.
- 🤖 **No AI.** The runbook is produced deterministically from what actually ran. Same session in, same runbook out.
- 📝 **Plain Markdown out.** Hand-editable, diff-able, and readable without runscribe installed.
- 🧹 **Secret-aware.** Built-in redaction scrubs common tokens, keys, and credentials before they land in a shared doc.

> **Why not just use `script`/asciinema or an AI tool?** Recorders give you an unsearchable replay, not an editable procedure. AI runbook generators send your shell activity to a model. `runscribe` gives you a clean, editable SOP *and* keeps everything on your machine.

## Install

```bash
pip install runscribe      # the command is `runscribe`
```

## Use

**1. Record** — run your commands as normal:

```bash
runscribe record
```

```
● recording — commands run for real; # note, ## section, exit to finish.
runscribe:myproject$ ## Deploy the API
runscribe:myproject$ # Make sure you're on the release tag first
runscribe:myproject$ git checkout v1.4.2
runscribe:myproject$ ./deploy.sh staging
runscribe:myproject$ exit
```

**2. Build** — turn the session into a runbook:

```bash
runscribe build --last -o deploy.md
```

```markdown
---
title: "Runbook — 20260706-141210"
created: "2026-07-06T14:12:10"
generated_by: runscribe
---

# Runbook — 20260706-141210

## Deploy the API

Make sure you're on the release tag first

<!-- runscribe: id=1 -->
```bash
git checkout v1.4.2
```

<!-- runscribe: id=2 -->
```bash
./deploy.sh staging
```
```

## How it works

`runscribe record` records each command, its working directory, exit code, timing, and (bounded) output to an append-only JSONL file under `.runscribe/sessions/`. On POSIX it feeds commands to a single long-lived shell, so `cd`, `export`, and shell variables **persist across steps** just like a real session; on Windows (or with `--subprocess`) it runs each command independently. `runscribe build` redacts secrets, drops navigation noise (`ls`, `pwd`, …), collapses immediately-repeated commands, and renders a Markdown runbook. Command steps are tagged with `<!-- runscribe: id=N -->` so a future `runscribe run` can re-execute exactly the runnable steps.

### Custom redaction rules

Drop a `.runscribe/redact.toml` next to your sessions to extend the built-in scrubbing:

```toml
# Extra regexes to scrub (matched spans become <REDACTED>).
patterns = ["INTERNAL-[0-9]{6}", "acme-[a-z]+-key"]

# Exact strings to always scrub (no regex needed).
literals = ["project-bluebird", "10.0.0.42"]
```

`runscribe build` picks it up automatically (or point at one with `--redact-config`).

## Roadmap

- **M1:** `record` + `build`. Per-command capture, secret redaction, Markdown output. ✅
- **M2:** persistent-shell capture (cd/export/vars persist), user-extensible `.runscribe/redact.toml`, smarter noise filtering. ✅
- **M3:** `runscribe run` — step-by-step execution with confirmations and `{{placeholders}}`.
- **M4:** full interactive-TUI (PTY) capture incl. native Windows, standalone `.exe`/binary (no Python needed), HTML export.

## Security & limits

Redaction is conservative but **not a guarantee**. Always skim a generated runbook before sharing it — `runscribe` cannot know that an unusual internal token is a secret. Recorded sessions under `.runscribe/` are git-ignored by default because their output may contain sensitive data.

## License

MIT © 2026 Hamza Mansoor

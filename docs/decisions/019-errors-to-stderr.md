---
id: "019"
title: Errors to stderr
status: accepted
date: 2026-05-06
supersedes: []
superseded_by: null
tags: [cli, errors, agent-first, unix]
---

# ADR-019: Errors to stderr

## Context

Issue #18 reports that `desk docs read --tab <bad-name>` writes its error message to **stdout** and exits 1 with empty stderr. The natural Unix-y fallback chain breaks as a result:

```bash
desk docs read $ID --tab Transcript || desk docs read $ID --tab Notes
```

When the first invocation fails, its error text gets written to stdout, then the fallback runs and writes its content to stdout, and the consumer sees the error concatenated with the fallback's output.

Inspecting the code, this is not a tab-resolution-specific bug. Every command module does `console = Console()` at module load (`commands/cal.py:23`, `commands/docs.py:22`, `commands/drive.py:24`, `commands/forms.py:21`, `commands/mail.py:27`, `commands/sheets.py:22`), and `rich.console.Console()` defaults to stdout. There are roughly 58 `console.print("[red]Error...")` sites across the command layer, plus all of the `print(json.dumps(structured_error(...)))` sites in `--json` mode and the auto-formatter in `agent.py:605`. Every one of them writes errors to stdout.

Two ADRs make the current behavior particularly hard to defend:

- **ADR-004 (Agent-First CLI)** treats agent composability and pipeline-friendliness as primary design goals. Errors on stdout corrupt `--json` consumers, break `cmd | jq`, and make `A || B` fallback chains output garbage.
- **ADR-018 (Tab Identifier Resolution)** introduces structured `TAB_NOT_FOUND` / `TAB_NAME_AMBIGUOUS` error payloads in service of those agent-first goals. The structured error idea is sound, but it lands on the wrong stream, which negates a chunk of its value.

No existing ADR specifies which stream errors are emitted on. This is a gap to close.

## Decision

**All error output — both human-readable text and structured JSON error envelopes — goes to stderr. Stdout is reserved for successful results.**

Concretely:

1. A single shared error console is introduced (`src/desk/console.py`):
   ```python
   from rich.console import Console
   error_console = Console(stderr=True)
   ```
   This replaces the per-module `console = Console()` *for error sites only*. Successful, human-readable output continues to use the existing per-module stdout console.
2. Every `console.print("[red]Error...")` call in `commands/*.py` is rewritten to `error_console.print(...)`. Same for `[red]Not authenticated[/red]`, validation errors, and similar failure-path human messages.
3. Structured JSON errors emitted via `print(json.dumps(structured_error(...)))` are rewritten to `print(json.dumps(...), file=sys.stderr)`. The `agent.py:emit_result` auto-formatter and the new tab-resolution emitters in `commands/docs.py` are updated alongside the bulk sites.
4. Successful JSON results continue to go to stdout. Successful human-readable text continues to go to stdout.
5. Exit codes are unchanged. `sys.exit(1)` (or its equivalents) still signals failure; the error payload on stderr is supplementary.

The contract becomes: **success → stdout, failure → exit ≠ 0 + stderr.** That holds for both `--json` and human modes.

### Scope

Applies to every command in every service module (`mail`, `drive`, `sheets`, `docs`, `cal`, `forms`), the auth flow, and `agent.py`'s `emit_result`. This is a one-shot, mechanical rewrite — no per-command judgement calls.

Out of scope: prompts (`click.confirm`, `Prompt.ask`) and progress indicators. These are interactive UI, not output, and their stream behavior is governed by the underlying library.

## Alternatives Considered

### Alternative 1: Status quo — errors on stdout

**Description**: Leave the current behavior in place. Document that callers must capture stdout to detect errors.

**Pros**:
- Zero churn
- Existing tests that read `result.output` for error text continue to pass without change

**Cons**:
- Breaks the canonical `A || B` shell pattern, as issue #18 demonstrates
- Corrupts `--json` consumers — a JSON error envelope arrives where success JSON was expected on the same stream
- Inconsistent with Unix convention and with every CLI Desk users will have used before
- Actively contradicts ADR-004's agent-friendliness goals

**Why rejected**: The bug-report-of-record (#18) is precisely about this behavior failing in real use. Defending it would mean defending a misfeature.

### Alternative 2: Errors to stderr in human mode, JSON errors to stdout

**Description**: Split the rule by output mode. Human error text → stderr (Unix-pure). Structured JSON error envelopes → stdout (so an agent that pipes `desk … --json | jq` can parse the failure payload from the same stream as success).

**Pros**:
- Agents using `cmd --json | jq` see the error envelope in `jq` regardless of success or failure
- Matches some tools (e.g. `kubectl` in certain modes) that prefer all structured output on a single stream

**Cons**:
- Two rules instead of one — caller must know which mode they're in to know which stream to read
- The `A || B` pattern still breaks under `--json` because the failure envelope still goes to stdout
- Most agents already check exit code first; reading stderr on failure is one extra step, not an obstacle
- Inconsistent: success-JSON and error-JSON on the same stream is exactly the mixing that broke #18 in human mode

**Why rejected**: The whole point of fixing this is to make the stream-discipline rule simple and predictable. A mode-dependent rule reintroduces the same class of bug for `--json` consumers.

### Alternative 3: Dual-emit (stdout + stderr) on errors

**Description**: Write the error payload to both streams.

**Pros**:
- Backwards compatible with any caller that scrapes stdout for error text
- Stderr-aware callers also see it

**Cons**:
- Doubles the output, breaks anything that counts bytes or hashes output
- Still corrupts pipelines: stdout still gets the error, so `A || B` still concatenates
- Conceptually wrong — there is one error, not two

**Why rejected**: Doesn't actually fix the bug, just adds more output.

### Alternative 4: New `--strict` flag that switches errors to stderr

**Description**: Default behavior unchanged. New flag opts callers in to stderr-on-error.

**Pros**:
- Zero risk of breaking existing callers

**Cons**:
- Two behaviors, two code paths, two test matrices to maintain
- Defaults to the broken behavior — most callers will never opt in and the bug stays alive
- Adds a flag that exists purely to compensate for a misfeature

**Why rejected**: Errors-to-stderr is the right default, not an opt-in. Behavior flags should toggle preferences, not papers over bugs.

## Consequences

### Positive

- **Issue #18's `A || B` pattern just works.** Both the simple case (human mode) and the JSON case behave identically: stdout is empty on failure, stderr carries the diagnostic, exit code is non-zero.
- **`--json` pipelines no longer break.** `desk … --json | jq …` only sees JSON success payloads on stdout; failures don't poison the parser.
- **Single rule.** "Success on stdout, errors on stderr" is one sentence and applies uniformly across services and modes.
- **Aligns ADR-018's structured errors with their intended use.** Agent callers that already check exit code now also have a clean stderr to parse for the structured envelope.
- **Aligns with ADR-004.** Agent-friendly composition was the goal; this removes a concrete obstacle to it.
- **No new flags, no new modes.** The change is purely about which file descriptor each existing print targets.

### Negative

- **`CliRunner`-based tests behave differently if they distinguish streams.** Existing tests use Click's default `mix_stderr=True`, so `result.output` still contains both streams; the bulk of the test suite is unaffected. Future tests that assert error text *must* be on stderr can opt into `mix_stderr=False`.
  - *Mitigation*: leave `mix_stderr` at its default for existing tests. Add stream-discipline regression tests with `mix_stderr=False` for the canonical cases (tab not found, auth failure).
- **External scripts that grep stdout for "Error:" miss errors after this change.** Any caller capturing stdout in a variable and looking for an error prefix will silently stop seeing errors.
  - *Mitigation*: this is exactly the behavior change the ADR is intended to make. Callers should rely on exit codes — which are unchanged — not on scraping stdout. The release note for this change calls it out explicitly.
- **One more module-level import in every command file.** Each `commands/*.py` adds `from desk.console import error_console`. Mechanical, not architectural.

### Neutral

- Rich-formatted color codes still work on stderr the same way they work on stdout (TTY detection is per-stream).
- No change to OAuth scopes, service-layer signatures, or command surface.

## Implementation Notes

### Files affected

**New file**:
- `src/desk/console.py` — exports `error_console = Console(stderr=True)`. Single source of truth for error-stream output.

**Modified — bulk rewrite of error sites**:
- `src/desk/commands/cal.py`
- `src/desk/commands/docs.py`
- `src/desk/commands/drive.py`
- `src/desk/commands/forms.py`
- `src/desk/commands/mail.py`
- `src/desk/commands/sheets.py`
- `src/desk/agent.py` — `emit_result` writes JSON errors to stderr
- `src/desk/auth.py` and `src/desk/cli.py` — failure-path prints

**Mechanical rules for the rewrite**:

1. Every `console.print("[red]Error: ...")` (and similar `[red]…[/red]` failure messages) → `error_console.print(...)`.
2. Every `print(json.dumps(structured_error(...)))` → `print(json.dumps(...), file=sys.stderr)`.
3. `[red]Not authenticated.[/red]` → stderr.
4. `[red]Failed: …[/red]` summaries on partial-failure paths → stderr.
5. Click's `UsageError` / `BadParameter` already write to stderr; leave them alone.
6. Successful, informational, and progress output (including `[green]✓[/green]` confirmations) → stays on stdout.

### Tests

- Add a regression test in `tests/test_commands/test_docs.py`: invoke `docs read --tab <bogus>` against a mocked client, assert `result.exit_code == 1`, assert error text appears on stderr (`mix_stderr=False`), assert stdout is empty.
- Add an analogous test for the JSON path: `--tab <bogus> --json`, assert the JSON envelope is on stderr and stdout is empty.
- Spot-check one site per service (mail, drive, sheets, cal, forms) with the same shape.
- Existing tests that read `result.output` for error text are unaffected — `CliRunner`'s default `mix_stderr=True` preserves their behavior.

### Documentation

- Issue #18 closes when the bulk rewrite lands.
- This ADR is referenced from ADR-018's "References" section as the binding decision on stream discipline for the structured error payloads it introduced.
- README's command examples don't change; the new contract is invisible to anyone who was already using the tool correctly.

## References

- [Issue #18](https://github.com/robpc/desk/issues/18) — original bug report
- ADR-004: Agent-First CLI Design — the agent-composability goals this ADR serves
- ADR-018: Tab Identifier Resolution — defined the structured error payloads whose stream this ADR fixes
- `src/desk/commands/docs.py:118-169` — the original `_emit_tab_not_found` / `_emit_tab_ambiguous` sites that prompted #18

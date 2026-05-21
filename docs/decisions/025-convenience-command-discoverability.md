---
id: "025"
title: Convenience Command Discoverability
status: accepted
date: 2026-05-21
supersedes: []
superseded_by: null
tags: [cli, agent-first, discoverability, deprecation]
---

# ADR-025: Convenience Command Discoverability

## Context

[ADR-002](002-command-composability.md) established the "primitives + named
commands" pattern: named commands (`archive`, `trash`, `mark-read`,
`star`, etc.) mirror Gmail-native UI actions, and the generic `modify`
command handles arbitrary label compositions. The intent was that an
agent reaching the limits of a named command would step up to `modify`.

In practice, agents don't step up. [PR #37](https://github.com/robpc/desk/pull/37)
made this visible: a contributor's agent, asked to archive *and* mark
read in one operation, extended the `archive` command with a new
`--mark-read` flag instead of finding `desk mail modify
--remove-label INBOX --remove-label UNREAD`. The PR's stated premise —
"previously required two separate commands" — is factually wrong;
`modify` has been the one-command answer the whole time. The agent
simply didn't find it.

Two specific failure modes show up in the diff:

1. **Naming attraction.** Named commands win agent attention because
   their verb matches the task. `desk mail unread` is the first hit for
   "get unread mail." `desk mail archive` is the first hit for "archive
   these." Once an agent locks onto a named command, the more powerful
   primitive (`mail search`, `mail modify`) is no longer in its frame.
2. **No upward navigation.** Nothing in a named command's `--help` or
   output points back at the primitive it wraps. When the agent's task
   grows ("archive AND mark read"), the natural move is to extend the
   leaf command rather than back out to the primitive. There is no
   in-tool signpost up the abstraction ladder.

Both failures share a root cause: **convenience commands hide their
backing primitive**. They look like leaves when they are thin wrappers
around `modify` / `search`. The cost is real — every future agent that
tries to extend a named command repeats the design drift.

There is also a category distinction ADR-002 elided:

| Category | Examples | Backing primitive | Gmail UI parallel |
|---|---|---|---|
| **Gmail-vocabulary action** | `archive`, `trash`, `mark-read`, `star`, `spam` | `mail modify` | Yes (toolbar buttons) |
| **Search shortcut** | `mail unread` | `mail search "is:unread"` | No |

Action commands have stable semantics rooted in Gmail's UI vocabulary
and are reasonable to keep. Search shortcuts are pure aliases that
encode an opinion about scope (e.g. "unread = `is:unread`" — but is
that `in:inbox`? `in:anywhere`? `not in:trash`?) and steer agents
away from the more controllable primitive.

## Decision

Three rules, codified together so the design intent is reviewable in
one place.

### 1. `--help` cross-reference rule

Every convenience command's help text ends with a `See also:` line
that names the equivalent `mail modify` (for label ops) or `mail
search` (for query ops) invocation. Example:

```
$ desk mail archive --help
Archive messages (remove from inbox).
...

See also: desk mail modify --remove-label INBOX <ids>
          (for compound label changes, e.g. archive + mark read)
```

The line is required, not optional. It costs one string per command,
lives in the first surface every agent and every human reads, and
gives the agent an explicit path back up the abstraction ladder.

### 2. Receipt `equivalent` field

The shared `operation_receipt()` helper in `src/desk/agent.py` gains
an optional `equivalent` parameter. When supplied, the receipt
includes:

```json
{
  "success": true,
  "operation": "archive",
  "equivalent": "desk mail modify --remove-label INBOX <ids>",
  ...
}
```

In human (non-JSON) output, the equivalent appears as a dim line under
the success message:

```
Archived 5 message(s)
  equivalent: desk mail modify --remove-label INBOX <ids>
  Undo: desk mail modify --add-label INBOX <ids>
```

Every successful operation now teaches the agent (and the human) the
primitive call that would have produced the same effect. Self-discovery
loop without changing any semantics. Both JSON and human modes carry
it so the lesson reaches both audiences.

Every Gmail-vocabulary action command in `commands/mail.py` is updated
to pass `equivalent=...` to `operation_receipt()`. Commands without a
single-call `modify` equivalent (e.g. operations that need two API
calls) omit the field — it's optional precisely so commands that
genuinely can't be replaced by a one-liner aren't forced to lie.

### 3. Search-shortcut commands are anti-pattern; deprecate `mail unread`

Search shortcuts are a different class from action commands. They
take a Gmail search operator (`is:unread`), wrap it in a verb-named
command, and bake an opinion about scope into the wrapper. PR #37's
attempt to narrow `mail unread` from `is:unread` to `is:unread
in:inbox` is the cleanest illustration: there's no canonical scope
choice, the convenience hides that fact, and any choice the maintainer
ships is wrong for half the workflows.

`mail unread` is the only such command in the current surface. It is
**deprecated** in this release with a stderr warning on every
invocation, and **scheduled for removal in the next minor version**.
Removal is tracked as a follow-up issue.

The replacement is `desk mail search "is:unread"` — exposing the full
Gmail search syntax to the caller, who is the only entity that knows
the right scope for their task. The deprecation warning points at
`mail search` and includes a worked example.

### 4. Deprecation pattern (new, codified here)

This is Desk's first user-facing deprecation. The pattern this ADR
sets:

- **Warning to stderr on every invocation** — visible to humans, easy
  for agents to detect, doesn't change behavior in the deprecating
  release.
- **Warning includes**: what's deprecated, the removal target version,
  the replacement command with a concrete example.
- **No env or flag to silence**, intentionally — silencing a
  deprecation warning is the kind of toggle that quietly preserves the
  problem the deprecation is meant to fix.
- **Removal**: the next minor version (e.g. if we're on 0.2.x, removal
  in 0.3.0). Tracked as a separate issue / PR; ADR-025 doesn't ship
  the removal itself.

Future deprecations follow the same shape.

## Alternatives Considered

### Alternative 1: Documentation-only fix (README aliases section)

**Description**: ADR-002 already says "Document common aliases in
README." Just do that more loudly.

**Pros**:
- Zero code change.

**Cons**:
- Agents don't read READMEs at the point of failure. They read
  `--help` for the command in front of them.
- The discoverability gap is *inside* the tool's surface; the fix
  belongs inside the surface too.
- Doesn't address the receipt-as-teaching opportunity.

**Why rejected**: Treats the symptom (agents don't know about
`modify`) without changing where they look (the named command's
output).

### Alternative 2: Remove all convenience commands, keep only `modify` + `search`

**Description**: Most aggressive simplification. `archive`, `trash`,
etc. all become `mail modify` recipes.

**Pros**:
- Single primitive; no discoverability gap because there's nothing to
  discover.
- Maximum consistency with ADR-002's spirit.

**Cons**:
- Loses Gmail-vocabulary alignment that ADR-002 specifically valued
  ("CLI vocabulary matches Gmail's vocabulary exactly").
- Breaks every current caller of `archive`/`trash`/`star`/etc. —
  massive churn for a category of commands whose vocabulary is stable
  and right.
- Agents that *do* find `archive` after the change can no longer use
  it; verbose `modify` invocations for every common case.

**Why rejected**: The named action commands aren't the problem.
Their inability to *signpost* `modify` is. Keep the names, add the
signposts.

### Alternative 3: Auto-suggest `modify` on extension attempts

**Description**: Detect when a named command is invoked with flags or
flag combinations that suggest the user is reaching for compound
behavior (e.g. unrecognized `--mark-read` on `archive`) and emit a
suggestion to use `modify`.

**Pros**:
- Catches the exact failure PR #37 illustrates at the point of error.

**Cons**:
- Requires defining "extension attempt" — fragile, easy to
  misclassify.
- Negative-feedback nudge rather than positive discovery. Agent has to
  fail first.
- Doesn't help the agent that *would* extend if it could — they'd
  just be more frustrated.

**Why rejected**: Positive signposting (in `--help`, in receipts) is
strictly better than negative correction at error time. Could
complement, but not as the primary fix.

### Alternative 4: Amend ADR-002 instead of writing a new ADR

**Description**: Add this as a new section in ADR-002.

**Pros**:
- One ADR to read for the full command-composability story.

**Cons**:
- ADR-002 is about *primitives existing alongside named commands*.
  This is about *making primitives reachable from named commands*.
  Adjacent but distinct concerns.
- Inflates ADR-002 with material the original author didn't write,
  blurring authorship and date.
- New ADR with explicit `References:` link is easier to surface in
  reviews ("does this conflict with ADR-025?").

**Why rejected**: Two ADRs are cheaper than one bloated one. Linkage
via References preserves coherence.

## Consequences

### Positive

- **Closes the discoverability gap PR #37 made visible.** Agents
  reading `--help` see the primitive immediately; agents reading
  their own JSON receipt see the equivalent call.
- **Establishes a deprecation pattern** for future Desk releases —
  not just `mail unread`.
- **Doesn't change semantics** of any current command. Pure additive
  for action commands; warning-only for `mail unread`.
- **Catches the next "Jessica's agent" automatically** — review-time
  rule that convenience commands must signpost their primitive.
- **Surfaces the action-vs-shortcut category distinction** that
  ADR-002 left implicit.

### Negative

- **Receipt schema gains an optional field**.
  - *Mitigation*: optional. Agents that don't read it are unaffected.
    Documented in the receipt's docstring.
- **`--help` output gets one extra line per command**.
  - *Mitigation*: it's the line that closes the discoverability gap;
    can't avoid the surface change without losing the fix.
- **`mail unread` deprecation breaks no one in this release, but
  removal in the next minor will break callers who ignore the
  warning**.
  - *Mitigation*: the warning is loud (every invocation, no silencer),
    points at the exact replacement, and gives one minor cycle of
    notice.

### Neutral

- The `equivalent` field is omitted from commands that genuinely
  require multiple API calls or have no clean one-liner equivalent —
  honest absence rather than forced cleverness.
- Future named commands ship with `equivalent=` from day one; this
  becomes part of the convention `--help`'s `See also:` enforces in
  review.

## Implementation Notes

### Files affected

- `src/desk/agent.py`:
  - `operation_receipt()` gains `equivalent: str | None = None` param.
    When set, included in the returned dict under the key
    `equivalent`.
- `src/desk/commands/mail.py`:
  - Every Gmail-vocabulary action command (`archive`, `trash`,
    `mark-read`, `mark-unread`, `star`, `unstar`, `label`,
    `remove-label`, `spam`, `not-spam`, `important`, `not-important`,
    plus the thread variants) gets:
    - A `See also:` line at the end of its docstring.
    - `equivalent=...` passed to `operation_receipt()`.
    - In non-JSON success path, a dim line under the success message
      with the equivalent call.
  - `mail unread`:
    - Warning to stderr on every invocation via `error_console.print()`.
    - Docstring updated to mark as deprecated and point at
      `mail search "is:unread"`.

- `tests/test_commands/test_mail.py`:
  - `archive`/`trash` smoke tests verify `equivalent` field appears in
    JSON receipt.
  - `mail unread` invocation emits warning on stderr.
  - At least one non-JSON test verifies the dim equivalent line
    appears under the success message.

### Out of scope

- Removing `mail unread`. Scheduled for the next minor; tracked
  separately so this PR is purely additive + warning.
- Receipt `equivalent` field on non-mail commands (drive, cal, docs,
  etc.). Same pattern would apply there if real workflows hit similar
  discoverability gaps; revisit when they do.
- Capabilities endpoint (per ADR-004) integration — the `equivalent`
  field is the primary discovery surface; capabilities can opt-in
  later.

## References

- [PR #37](https://github.com/robpc/desk/pull/37) — the diagnostic
  contribution that made this gap visible
- [ADR-002](002-command-composability.md) — primitives + named
  commands (this ADR extends, doesn't supersede)
- [ADR-003](003-unified-workspace-cli.md) — "toolkit, not productivity
  app"
- [ADR-004](004-agent-first-cli.md) — agent-first CLI principles
- [ADR-019](019-errors-to-stderr.md) — stream discipline for the
  deprecation warning

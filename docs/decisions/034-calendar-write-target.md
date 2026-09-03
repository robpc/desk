---
id: "034"
title: Explicit Calendar Target on Calendar Write Commands
status: accepted
date: 2026-09-03
supersedes: []
superseded_by: null
tags: [calendar, cli, agent-first]
---

# ADR-034: Explicit Calendar Target on Calendar Write Commands

## Context

[ADR-023](023-multi-calendar-query.md) added a repeatable `-c / --calendar`
to the four read-side calendar commands. Its "Out of scope" section reads:

> Write-side commands (`create`, `update`, `delete`) — they already
> accept `--calendar` as a single value; cross-calendar mutations aren't
> on the table here.

**That premise was wrong.** The `CalendarClient` methods take a
`calendar_id` parameter, but the Click commands never exposed one and
never passed anything, so every write silently used the
`calendar_id: str = "primary"` default. The reads got multi-calendar
support; the writes were left addressing exactly one calendar, and the
ADR recorded the gap as already-closed. See
[`robpc/desk#88`](https://github.com/robpc/desk/issues/88).

The result is an asymmetry with two distinct costs:

1. **Events can only be created on the primary calendar.** A shared
   family or team calendar is readable but not writable.

2. **`update` and `delete` take a bare `EVENT_ID`, which is not a
   complete address.** A Google Calendar event id is only meaningful
   together with the calendar holding it — `events.update` and
   `events.delete` both require a `calendarId`. `desk cal next -c
   "Family" --json` hands back an event that `desk cal update` cannot
   reach. Worse, it does not fail cleanly: the id is looked up against
   `primary`, where it does not exist, so the user sees a confusing
   404 rather than "wrong calendar."

The second cost is the sharper one, and it makes this a functional gap
rather than a convenience one: there is a class of events desk can show
you and cannot touch.

For agent callers the gap cannot even be expressed. A wrapper exposing
these commands as tools has no argument for "which calendar," so the
restriction has to live in prose the model is asked to respect. An agent
that offers to put an event on a named calendar is making a promise the
CLI cannot keep, and nothing fails loudly when it breaks — the event just
lands on primary.

## Decision

Add a **single-valued** `-c / --calendar` option to `cal create`,
`cal update` and `cal delete`, resolved through the same
`_resolve_calendars` helper the read commands use.

- **Accepted values** are identical to the read side: a calendar ID, a
  friendly `summary` name from `desk cal list` (case-insensitive), or the
  literal `primary`.
- **Omitted** → `primary`, exactly as today. Existing callers and scripts
  are unaffected.
- **Not repeatable.** A write targets one calendar. Passing `-c` twice is
  rejected with `INVALID_INPUT` before any lookup or write.

  This needs an explicit check rather than just leaving the option
  scalar: Click's default for a non-`multiple` option is to keep the
  **last** value and say nothing. For a read that is merely surprising;
  for a write target it is the same silent wrong-calendar write this ADR
  exists to prevent. So the option is declared `multiple=True` and
  arity is enforced in `_resolve_write_calendar`, which turns the
  ambiguity into an error the caller can see.
- **Resolution errors** are the existing `INVALID_INPUT` structured error
  from `_emit_resolution_error`, unchanged.

`cal delete` resolves the calendar **once** and uses the same resolved ID
for both its confirmation `get_event` lookup and the `delete` call, so the
event previewed in the confirmation prompt is always the event that gets
deleted.

### Out of scope

- **Moving an event between calendars.** That is Google's
  `events.move`, a different operation with different semantics
  (notifications, id stability). `-c` selects where an event *lives*, it
  does not relocate one. Captured as
  [idea 080](../ideas/080-calendar-event-move.md).
- **`cal respond` and `cal invitations`.** Invitations arrive on the
  calendar they were sent to; a target flag there needs its own thinking
  about what a non-primary invitation means.
- **Defaulting to something other than `primary`.** A configurable
  default write calendar is a separate decision.

## Alternatives Considered

### Alternative 1: Make `-c` repeatable, matching the read side

**Description**: Accept `multiple=True` on the write commands for
symmetry with `today` / `week` / `next` / `find`.

**Pros**:
- One consistent option shape across every `cal` command.
- `_resolve_calendars` returns a list already; no adapter needed.

**Cons**:
- Meaningless for `create` — "create this event on three calendars" is
  three distinct events with three distinct ids, and one receipt cannot
  describe them.
- Actively dangerous for `delete` — an event id valid on two calendars
  would delete both from one confirmation prompt.
- Forces every caller to reason about a list where the domain has exactly
  one value.

**Why rejected**: Symmetry of *spelling* is worth less than honesty about
arity. Reads fan out; writes do not. Rejecting a second `-c` is a better
contract than accepting one and quietly ignoring it.

### Alternative 2: Qualified event ids (`calendar:event_id`)

**Description**: Let `update` and `delete` take
`family14493...@group.calendar.google.com:abc123` as a single argument.

**Pros**:
- One token carries the complete address; nothing to forget.
- Round-trips naturally if `cal next --json` emitted the qualified form.

**Cons**:
- Calendar IDs contain `@` and `.`; adding `:` as a delimiter invents a
  desk-specific encoding on top of Google's ids, which ADR-002 warns
  against.
- Breaks every existing caller that passes a bare id.
- The `calendar_id` field ADR-023 already puts on each event is the
  provenance mechanism; a second, differently-shaped one is redundant.

**Why rejected**: Invented vocabulary (ADR-002), and a breaking change to
solve a problem a flag solves additively.

### Alternative 3: Auto-discover which calendar holds the event

**Description**: On `update` / `delete`, if the id is not found on
primary, search every calendar from `cal list` for it.

**Pros**:
- No new flag; bare ids "just work."

**Cons**:
- N API calls per write, where N is the user's calendar count.
- Ambiguous when an id resolves on more than one calendar (shared events
  and copies), and the failure mode is a silent write to the wrong one.
- Magic that hides the calendar dimension exactly when a destructive
  operation most needs it visible.

**Why rejected**: Guessing the target of a delete is the wrong place to
be clever. ADR-004 wants contracts an agent can state, not behavior it
has to predict.

## Consequences

### Positive

- **Shared calendars become writable.** `desk cal create "Dinner" -c
  Family ...` works, closing the read/write asymmetry.
- **Events surfaced by a read are reachable by a write.** The
  `calendar_id` on every event from ADR-023 now feeds directly back into
  `-c`, so a read → write round trip composes.
- **The constraint is expressible to agents.** A tool wrapper gets a real
  parameter instead of a prose caveat, and a wrong value fails loudly at
  resolution rather than writing to the wrong calendar.
- **Additive.** Omitting `-c` is byte-for-byte today's behavior.

### Negative

- **A friendly name costs one extra `calendarList.list` call** before the
  write.
  - *Mitigation*: unchanged from the read path — only on a non-ID value,
    and IDs and `primary` short-circuit before any network call.
- **`-c` on `update` / `delete` is easy to forget**, and forgetting it
  still yields a 404 against primary.
  - *Mitigation*: the failure is loud and non-destructive. Making the
    flag required would break every existing caller for the sake of a
    case the error message already explains.

### Neutral

- `_resolve_calendars` is reused as-is and still returns a list; the
  write commands take `[0]` after Click has enforced single-arity. No
  change to the read path.

## Implementation Notes

### Files affected

- `src/desk/commands/cal.py`:
  - New `_WRITE_CALENDAR_OPTION_HELP` constant — the read-side help text
    advertises repeatability, which is wrong here.
  - New helper `_resolve_write_calendar(client, value, as_json) -> str`
    wrapping `_resolve_calendars` for the single-value case.
  - `create`, `update`, `delete` each gain `-c / --calendar`
    (`multiple=True` for arity checking, semantically single-valued) and
    thread the resolved ID into the corresponding `CalendarClient` call.
  - `delete` additionally passes it to its `get_event` confirmation
    lookup.
  - Receipts and dry-run previews include the resolved `calendar_id`, and
    the `undo_command` on both embeds `-c <resolved-id>` so an undo
    round-trips to the calendar actually written to rather than to
    `primary`.

- `src/desk/services/calendar.py`: **no changes.** Every method already
  accepts `calendar_id`.

- `tests/test_commands/test_cal.py`: create/update/delete with an ID,
  with a friendly name, and with the flag omitted (asserting `primary`);
  delete resolving once for both calls; unknown name → `INVALID_INPUT`;
  repeated `-c` → `INVALID_INPUT` with nothing written; dry-run undo
  carrying the resolved calendar.

## References

- [Issue #88](https://github.com/robpc/desk/issues/88) — bug report
- [ADR-023](023-multi-calendar-query.md) — read-side `--calendar`; this
  ADR corrects its out-of-scope note
- [ADR-002](002-command-composability.md) — no invented vocabulary
- [ADR-004](004-agent-first-cli.md) — contracts an agent can express
- [ADR-019](019-errors-to-stderr.md) — resolution errors to stderr
- [Google Calendar `events.insert`](https://developers.google.com/calendar/api/v3/reference/events/insert)

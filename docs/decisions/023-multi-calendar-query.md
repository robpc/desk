---
id: "023"
title: Multi-Calendar Query Support via Repeatable `--calendar`
status: accepted
date: 2026-05-18
supersedes: []
superseded_by: null
tags: [calendar, cli, agent-first]
---

# ADR-023: Multi-Calendar Query Support via Repeatable `--calendar`

## Context

Every `desk cal` read command (`today`, `week`, `next`, `find`) operates on
the user's primary calendar. `desk cal list` enumerates all calendars the
user has access to — shared family calendars, partner calendars, calendars
shared in from coworkers — but none of those can be the target of a
query. The only way to look at a non-primary calendar today is to leave
Desk.

A concrete trigger: a Monday-morning calendar brief that surfaces
overlapping commitments — primary plus a shared family calendar so the
agent can see when a kid has a school event or a weekend dinner is
booked. Without a flag, the brief silently misses anything not on the
primary calendar. See
[`robpc/desk#27`](https://github.com/robpc/desk/issues/27).

Calendar IDs are unfriendly to type
(`family14493193352610494384@group.calendar.google.com`), so we want both
identifiers and human-readable names from `desk cal list` to work.

## Decision

Add a repeatable `-c / --calendar` option to the four read-side calendar
commands (`today`, `week`, `next`, `find`). The option accepts any of:

1. **A calendar ID** — `family14493...@group.calendar.google.com`
2. **A friendly name** — the `summary` field as printed by `desk cal list`,
   matched **case-insensitively** (`Family`, `family`, `FAMILY` all work)
3. **The literal `primary`** — the user's primary calendar

Behavior:

- **Omitted flag** → default to `["primary"]`. Existing scripts and agents
  see no change.
- **One `-c`** → single-calendar mode, identical to today except for the
  resolution step and the new `calendar_id` field on each event.
- **Two or more `-c`** → multi-calendar mode. Each calendar is queried
  independently, results are merged, sorted chronologically by start
  time, and returned as a single events list.

### Resolution rules

- The flag value is first compared against calendar IDs exactly. If it
  matches, that ID is used.
- Otherwise, the value is compared against `summary` strings from
  `desk cal list` case-insensitively. A unique match wins.
- **Ambiguous match** (the same friendly name appears on two calendars)
  is a hard error, structured as `INVALID_INPUT` with a suggestion listing
  the matching IDs.
- **No match** is `INVALID_INPUT` with a suggestion to run
  `desk cal list`.

### `calendar_id` on every event

Every returned event gains a top-level `calendar_id` field, populated
with whatever resolved ID the event came from (the literal string
`"primary"` is preserved when that's what the user asked for, so output
matches input). Single-calendar mode is unaffected by adding this field —
agents that ignored it before continue to work.

### Merging and ordering

- Results merge by start time, ascending, using Calendar's reported
  `start.dateTime` or `start.date` (whichever the event has). All-day
  events sort by their `date`, which compares correctly against ISO
  datetime strings for the date boundaries that matter.
- `max_results` applies **per calendar**, not to the merged total. Two
  `-c` flags with `--max 10` may return up to 20 events. Documented in
  `--help`. Callers that need a tight cap can run separate calls.

### Pagination

- **Single `-c`**: `--page-token` works as today.
- **Multiple `-c`**: `--page-token` is rejected with `INVALID_INPUT`.
  Per-calendar pagination is available by issuing separate single-`-c`
  calls. A future ADR can introduce a structured
  `nextPageTokens: {calendar_id: token}` if real usage demands it.

### Out of scope

- `freebusy` (it has its own multi-calendar semantics in the Google API
  and isn't a `list`-shaped read).
- Write-side commands (`create`, `update`, `delete`) — they already
  accept `--calendar` as a single value; cross-calendar mutations aren't
  on the table here.
- Per-calendar pagination tokens in the response (deferred per the issue).

## Alternatives Considered

### Alternative 1: Shell-loop and merge externally

**Description**: Keep the API single-calendar; document a `for cal in
...; do desk cal today -c $cal --json; done | jq -s 'sort_by(.events)'`
pattern.

**Pros**:
- Zero CLI changes.

**Cons**:
- Pushes orchestration onto every caller, especially agents.
- Loses the `calendar_id` provenance unless the wrapping shell injects
  it, which agents are inconsistent at.
- Doesn't address the friendly-name resolution gap — caller must already
  know the IDs.

**Why rejected**: This is the exact "agents shouldn't reimplement
pagination/orchestration" anti-pattern [ADR-006](006-query-based-bulk-operations.md)
calls out for mail. Same logic applies here.

### Alternative 2: Auto-merge "primary + every writable shared calendar"

**Description**: Drop the flag entirely; have `desk cal today` always
return events across every calendar the user can write to.

**Pros**:
- Zero new flags.

**Cons**:
- Magic default that nobody asked for; users with many shared calendars
  see unrecognizable noise.
- Backwards-incompatible for anyone already scripting against `today`.
- Loss of intent — sometimes I really do want only primary.

**Why rejected**: The issue explicitly calls this out as "too magic."
Defaults should match user intent, and "primary only" matches everyone's
historical expectation.

### Alternative 3: Separate `cal multi` subcommand

**Description**: `desk cal multi today -c primary -c family ...`

**Pros**:
- Keeps existing commands untouched.

**Cons**:
- Doubles the command surface. Agents now have to choose between two
  command paths for the same semantic operation.
- Inconsistent: every read command would need a `multi` twin.

**Why rejected**: A repeatable flag on the existing commands covers the
single and multi cases with one API. ADR-002 prefers a primitive over
parallel command trees.

### Alternative 4: Single `-c` accepting a CSV

**Description**: `desk cal today -c primary,Family,family1449...`

**Pros**:
- One flag.

**Cons**:
- Calendar IDs contain `@`, friendly names can contain commas (a calendar
  named "Boss, John's calendar" exists), so CSV inside a flag is
  ambiguous to parse safely.
- Doesn't compose with shell loops that want to add one extra `-c X`.

**Why rejected**: Repeatable flags are the right shape for "0..N
discrete tokens." CSV inside a flag is fragile.

## Consequences

### Positive

- **The Monday-morning brief works.** Primary plus family in one call,
  sorted, with provenance.
- **Agent-friendly resolution.** Friendly names from `cal list` work
  directly; agents don't have to round-trip IDs.
- **No regression for existing callers.** Omitted flag → primary, same as
  today. The new `calendar_id` field is additive in JSON.
- **One flag covers single and multi modes.** No parallel command tree.

### Negative

- **Resolution requires one extra `calendarList.list` call** the first
  time a friendly name appears in any invocation.
  - *Mitigation*: cached on the client for the lifetime of the command.
    Single API call, ~1KB payload.
- **`max_results` semantics shift from "total" to "per calendar"** in
  multi-calendar mode.
  - *Mitigation*: documented in `--help` and the ADR; matches the
    semantics of "ask each calendar for N independently."
- **`--page-token` rejected in multi-calendar mode** is a step short of
  full pagination support.
  - *Mitigation*: per the issue ("each `-c` paginates independently for
    now; combiner just exhausts each"). Per-calendar pagination is the
    documented workaround.

### Neutral

- Resolution is case-insensitive but casing-preserving in output: the
  `calendar_id` field surfaces the resolved ID, not the user's input.
  Predictable for agents.

## Implementation Notes

### Files affected

- `src/desk/services/calendar.py`:
  - `_parse_event(event, calendar_id=None)` — accept the source calendar
    ID and surface it on every event dict.
  - `today`, `week`, `next`, `find`, `_list_events` — propagate the
    resolved `calendar_id` through to `_parse_event`. No new public
    methods.

- `src/desk/commands/cal.py`:
  - New helper `_resolve_calendars(client, raw: tuple[str, ...]) ->
    list[str]`. Handles the empty-tuple → `["primary"]` default, the
    `cal list`-based name resolution, ambiguous-match error,
    no-match error.
  - New helper `_query_calendars(client, raw: tuple[str, ...], page_token,
    fn, **kwargs)`. Performs the resolution, validates `page_token`
    compatibility, calls `fn` per calendar, merges and sorts by start
    time.
  - `today`, `week`, `next`, `find` each gain `-c/--calendar
    calendar TEXT` as `click.option(... multiple=True)`. Existing
    options unchanged.

- `tests/test_services/test_calendar.py`:
  - `_parse_event` includes `calendar_id` when passed.
- `tests/test_commands/test_cal.py`:
  - `today -c primary` returns events with `calendar_id="primary"`.
  - `today -c Family -c primary` resolves `Family` and merges results
    sorted by start time.
  - Ambiguous friendly name returns structured INVALID_INPUT.
  - Unknown friendly name returns structured INVALID_INPUT.
  - `today -c primary -c Family --page-token X` rejected.

### Resolution helper sketch

```python
def _resolve_calendars(client, raw: tuple[str, ...]) -> list[str]:
    if not raw:
        return ["primary"]

    catalog = None  # lazy: only fetched if a non-ID name appears
    resolved: list[str] = []
    for value in raw:
        if value == "primary" or "@" in value:
            resolved.append(value)
            continue
        if catalog is None:
            catalog = client.list_calendars()
        matches = [
            c for c in catalog
            if c.get("summary", "").casefold() == value.casefold()
        ]
        if len(matches) == 1:
            resolved.append(matches[0]["id"])
        elif not matches:
            raise click.BadParameter(...)
        else:
            raise click.BadParameter(...)  # ambiguous
    return resolved
```

(Click's `BadParameter` already routes to stderr per
[ADR-019](019-errors-to-stderr.md). Structured-JSON callers get
`structured_error(INVALID_INPUT, ...)` through the same
`_handle_api_error` path the file already uses.)

## References

- [Issue #27](https://github.com/robpc/desk/issues/27) — bug report and
  proposal
- [ADR-002](002-command-composability.md) — primitives over parallel
  commands
- [ADR-004](004-agent-first-cli.md) — agent-friendly contracts (provenance
  on every record)
- [ADR-006](006-query-based-bulk-operations.md) — CLI handles
  orchestration, not the agent
- [ADR-019](019-errors-to-stderr.md) — stream discipline for
  resolution-failure errors
- [Google Calendar `calendarList.list`](https://developers.google.com/calendar/api/v3/reference/calendarList/list)

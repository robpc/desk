---
id: "035"
title: Calendar Display Name Prefers `summaryOverride`
status: accepted
date: 2026-09-03
supersedes: []
superseded_by: null
tags: [calendar, cli, agent-first]
---

# ADR-035: Calendar Display Name Prefers `summaryOverride`

## Context

`cal list` reports a calendar's `summary` and drops `summaryOverride`
entirely. Google's `calendarList` entries carry both:

- `summary` — the calendar's own title, set by its **owner**.
- `summaryOverride` — the name **this** user gave it, which is what
  Google's own UI displays.

`summaryOverride` is present only when the user has renamed the calendar,
so the display name is `summaryOverride or summary`. Dropping it means a
renamed calendar shows the owner's title, not the name the user chose.

This is more than cosmetic. Per [ADR-023](023-multi-calendar-query.md),
`-c/--calendar` resolves friendly names against this same list, so the
name a user must *type* is the one desk knows rather than the one they
*see*. And an agent that reads these names also says them back — "I'll
put it on gvc.wdc@gmail.com" instead of naming the person, which is both
worse writing and an address surfacing where a name belongs. See
[`robpc/desk#92`](https://github.com/robpc/desk/issues/92).

### Investigation note

The issue was filed against a calendar displaying as a bare Gmail
address. A first read of that account's `calendarList` showed **no**
`summaryOverride` on it — or on any of its ten calendars — which
suggested the display name lived somewhere the `calendar` scope cannot
reach. Within that scope there is indeed no other name available: not on
the `calendars.get` resource, and not on any event's `organizer`,
`creator` or `attendees` `displayName`.

A second read minutes later returned `summaryOverride: "Grace Cannon"`,
with a changed etag (`...711` → `...151`). Between the two reads the only
thing that happened was the account owner opening that calendar's
settings page in the web UI — they report not editing the Name field, and
not having touched the calendar in over a decade.

The likeliest reading is that Google had been rendering a display name
for this person-calendar without ever persisting it, and materialized it
onto the `calendarList` entry when the settings page was opened. That is
inference, not something the API confirms; what is certain is that the
field was absent, then present, with no deliberate rename in between.

The conclusion is the one the issue proposed: honoring `summaryOverride`
is the fix, and it resolves the reported case. The note is kept for two
reasons. It bounds the fix — a calendar with no `summaryOverride` still
has no human-readable name anywhere in the `calendar` scope, and covering
that would need Contacts and a new OAuth scope
([idea 081](../ideas/081-person-calendar-contact-names.md)). And it
records that the field can appear without a deliberate rename, so
"absent" is not a stable property of a calendar and should not be read as
"this user never wanted a name here."

## Decision

`list_calendars` returns **two** name fields on every entry:

- **`summary`** — the display name: `summaryOverride` when set, else the
  calendar's own `summary`. This is the field callers already read, and
  it now holds the name the user would recognize.
- **`summary_original`** — the calendar's own title, always present.
  Equal to `summary` when no override is set.

Both keys are **always** present. A conditional field would be smaller
output but a less predictable contract; ADR-023 set the precedent of
adding `calendar_id` unconditionally for the same reason.

### Name resolution accepts either name

`_resolve_calendars` matches a `-c` value against **both** `summary` and
`summary_original`, case-insensitively. A user who renamed a calendar can
type the name they see; a script written against the owner's title keeps
working. This extends ADR-023's resolution rules, which specified
`summary` alone.

If one value matches on the display name and a *different* calendar
matches on its original title, that is an ambiguous match and gets the
existing `INVALID_INPUT` error listing the candidates — the same rule
ADR-023 already applies to duplicate names.

### Human-readable output

`cal list` prints the display name. When an override is in play, the
owner's title is shown dimmed alongside the ID, so the mapping stays
discoverable:

```
Grace
  gvc.wdc@gmail.com — owner's title: gvc.wdc@gmail.com
```

## Alternatives Considered

### Alternative 1: Add `summary_override`, leave `summary` alone

**Description**: Surface the raw API field under its own key and let
callers apply the `or` themselves.

**Pros**:
- Zero change to an existing field's meaning; nothing can regress.
- Mirrors Google's resource shape exactly.

**Cons**:
- Every caller must know the precedence rule and apply it, and agents
  inconsistently will. The one field everybody already reads stays wrong
  in exactly the case that matters.
- Pushes a display concern onto each caller — the same "agents shouldn't
  reimplement the obvious" objection [ADR-006](006-query-based-bulk-operations.md)
  raises for pagination.

**Why rejected**: The default field should hold the right answer.
Correctness by opt-in is not correctness.

### Alternative 2: Replace `summary` with the override and expose nothing else

**Description**: `summary = summaryOverride or summary`, no second field.

**Pros**:
- Smallest possible output; one obvious name.

**Cons**:
- The owner's title becomes unreachable. A caller reconciling desk's
  output against another Calendar client — or against the API directly —
  has no way to see the canonical name.
- Breaks any existing script matching on the owner's title, with no
  migration path.

**Why rejected**: Keeping `summary_original` costs one key and preserves
both the round trip and existing scripts.

### Alternative 3: Resolve person-calendars through the People API

**Description**: Look the calendar ID up in Google Contacts and use the
contact's name.

**Pros**:
- Would fix the symptom actually reported in #92.

**Cons**:
- Requires a new OAuth scope (`contacts.readonly`), which forces a
  re-consent for every existing user — a real cost under
  [ADR-001](001-oauth-credential-strategy.md)'s user-owned-credentials
  model.
- Reading a user's contacts to render a calendar list is a large privacy
  expansion for a naming convenience.
- An extra API call, or a cache, on a command that is currently one call.

**Why rejected**: Out of proportion to the problem, and a scope
expansion deserves its own decision rather than riding along in a bug
fix. Captured as idea 081.

## Consequences

### Positive

- **Renamed calendars show the name the user chose**, in both JSON and
  the human-readable listing.
- **`-c` accepts either name**, so what a user sees is what they can
  type — and existing scripts using the owner's title keep working.
- **Agents say names, not addresses**, when reporting which calendar they
  used.
- **Additive JSON.** `summary` keeps its type and meaning for every
  calendar without an override, which on most accounts is all of them.

### Negative

- **`summary` changes meaning for renamed calendars** — a caller that
  deliberately wanted the owner's title now needs `summary_original`.
  - *Mitigation*: that field exists precisely for this, and the case is
    rare enough that no caller can currently depend on it — before this
    change the override was never surfaced at all.
- **A calendar could now be reachable by two names**, so an ambiguity is
  possible where none existed.
  - *Mitigation*: routed through ADR-023's existing ambiguous-match
    error, which lists the candidate IDs.

### Neutral

- Accounts with no renamed calendars see `summary == summary_original`
  everywhere and no behavior change at all.

## Implementation Notes

### Files affected

- `src/desk/services/calendar.py`: `list_calendars` emits `summary`
  (override-preferring) and `summary_original`.
- `src/desk/commands/cal.py`: `_resolve_calendars` matches against both
  names; `list_calendars` prints the display name and shows the owner's
  title when it differs.
- `tests/`: override present / absent, resolution by either name,
  ambiguity across the two fields, and the printed output.

## References

- [Issue #92](https://github.com/robpc/desk/issues/92) — bug report
- [ADR-023](023-multi-calendar-query.md) — friendly-name resolution, whose
  rules this extends
- [ADR-001](001-oauth-credential-strategy.md) — why a new scope is costly
- [Idea 081](../ideas/081-person-calendar-contact-names.md) — the People
  API path, deferred
- [Google `calendarList` resource](https://developers.google.com/calendar/api/v3/reference/calendarList)

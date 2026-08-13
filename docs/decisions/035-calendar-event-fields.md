---
id: 035
title: Calendar Event Fields — Conferencing, Guest Permissions, Notification Control
status: accepted
date: 2026-07-31
supersedes: []
superseded_by: null
tags: [cal, api, agent-first]
---

# ADR-035: Calendar Event Fields — Conferencing, Guest Permissions, Notification Control

## Context

Issue #80, found while scripting recurring training invites: `desk cal create` / `update`
cover title, time, description, and attendees, but several Calendar fields that come up on
almost any real invite force a fall back to the web UI.

Verified against the code:

- **No conferencing.** `create()` builds a body of only summary/start/end/description/
  attendees (`calendar.py:158-166`). An invite made with Desk has no join link, which makes
  it unusable for a remote meeting without a manual UI edit.
- **`sendUpdates` is hardcoded to `"all"`** in four places — create (`calendar.py:174`),
  update (`:278`), delete (`:210`), respond (`:517`). This is worse than the issue reports:
  it's not that you can't opt into notifying, it's that you can never opt *out*. You cannot
  stage an event quietly, and you cannot delete an event without mailing a cancellation to
  every attendee.
- **No guest permission flags** — `guestsCanSeeOtherGuests`, `guestsCanInviteOthers`,
  `guestsCanModify`. Hiding the guest list matters whenever a mailing list or a large
  audience is invited, and the API default exposes it.
- **No `--location`, visibility, or free-vs-busy.**

One gap the issue didn't mention: `_parse_event()` (`calendar.py:382-409`) drops
`hangoutLink` and `conferenceData` entirely, so Desk cannot even *display* a Meet link on
events that already have one, whoever created them. Read-side, no new scope.

None of this needs a scope change — `auth/calendar` already covers it.

## Decision

### 1. Surface the conference link on read

`_parse_event()` gains `meetLink` (from `hangoutLink`) and `conferenceId` (from
`conferenceData.conferenceId`). Every read path — `today`, `week`, `next`, `find`,
`get_event` — gets it for free.

`conferenceId` is included because it is the handle the Meet API addresses a space by
(`spaces/{meetingCode}`), which is what makes ADR-036 composable from the CLI.

### 2. `--meet` on `create` and `update`

Attaches a Google Meet conference via `conferenceData.createRequest` with
`conferenceDataVersion=1` on the insert/update. On `update` this is the "add a Meet link to
an existing event" case, which the issue calls out as common on its own.

`--meet` is idempotent on update: an event that already has a conference is left alone
rather than having a second one requested.

The `requestId` for `createRequest` is derived from the event, not random — Calendar treats
it as an idempotency key, and Desk scripts get retried.

### 3. Guest permission flags, named for what they do

```
--hide-guest-list        guestsCanSeeOtherGuests: false
--no-guest-invites       guestsCanInviteOthers: false
--guests-can-modify      guestsCanModify: true
```

Only sent when the flag is passed, so Google's defaults stand otherwise.

### 4. `--send-updates [all|external-only|none]`, defaulting to `all`

Applies to `create`, `update`, `delete`, and `respond`. **The default remains `all`,
preserving today's hardcoded behavior** — this is deliberately not a behavior change, only
a way to opt out.

The CLI spells the middle value `external-only`; the API spells it `externalOnly`. We take
the hyphenated form because every other Desk flag value is hyphenated, and map it at the
service boundary.

### 5. `--location`, `--visibility`, `--free`

`--visibility [default|public|private]` maps to the API's `visibility`. `--free` sets
`transparency: transparent` (free); its absence leaves the event opaque (busy).

`--free` rather than `--transparency=transparent`: "transparency" is Google's field name but
it's opaque jargon at a CLI, and free-vs-busy is what the UI calls it. This is a rename of
an existing Google concept, not invented vocabulary — ADR-002 is about not inventing
concepts Google doesn't have, and "Free" is literally the Calendar UI's label.

### 6. Document the per-guest-role limitation

`desk cal create --help` states that Calendar has no per-guest co-organizer role
(`guestsCanModify` is event-wide) and that Meet co-hosts aren't settable through the
Calendar API. Issue #80 asked for this explicitly so the limitation reads as Google's, not
Desk's.

## Alternatives Considered

### Alternative 1: `--conference` / `--add-conference` instead of `--meet`

**Description**: Name the flag after the API field (`conferenceData`) rather than the
product.

**Pros**:
- Matches the API vocabulary exactly (ADR-002)
- Would extend to non-Meet conference solutions

**Cons**:
- Users and agents think "Meet", and the request in #80 is literally `--meet`
- Desk only ever requests `hangoutsMeet`; the generality is theoretical
- "Conference" is ambiguous in a calendar context (a conference *event*?)

**Why rejected**: `--meet` is what the product is called in the Calendar UI, so this is
Google's vocabulary too — just the user-facing half.

### Alternative 2: Make `--send-updates none` the default

**Description**: Default to quiet, require opting into notifications.

**Pros**:
- Safer default — no accidental mail to attendees, which is irreversible
- Matches the "stage quietly, notify later" flow that motivated the issue

**Cons**:
- Silently changes the behavior of every existing script and agent workflow
- Surprising: creating an invite that nobody is told about is rarely what's meant
- Diverges from the Calendar UI, which notifies by default

**Why rejected**: too large a behavior change to smuggle into a feature addition — and on
reflection, the premise was weaker than it looked. The Calendar UI's own default action isn't
a blunt "mail everyone": adding one guest and taking the primary button only notifies that
guest, not the existing attendee list. That scoping happens inside Google's backend under
`sendUpdates=all` — the API has no fourth value for "only whoever's actually affected" — so
`all` likely already reproduces the UI's default lean for the cases that matter (an add) and
is *correctly* unscoped for the cases where every attendee genuinely needs to know (a deletion,
a reschedule). Revisited and closed with the user 2026-08-12: leave the default at `all`.

### Alternative 3: A single `--guest-permissions` taking a comma list

**Description**: `--guest-permissions no-see-others,no-invite`.

**Pros**:
- One flag instead of three

**Cons**:
- Invents a vocabulary for values that have real API names
- Harder to discover from `--help`; no per-value help text
- Awkward to express the tri-state (unset vs true vs false)

**Why rejected**: three boolean flags are more discoverable and map 1:1 to API fields.

### Alternative 4: Fold Meet artifact settings (`--auto-record`) into `cal create`

**Description**: What issue #81 suggests — `desk cal create --meet --auto-record --cohost ...`.

**Pros**:
- One command for the whole "set up a recorded meeting" flow
- Fewer round trips for the caller

**Cons**:
- Makes a Calendar command call the Meet API — precisely the cross-service composition
  ADR-003 forbids
- Bundles two failure modes: a partial success (event created, artifact config rejected)
  has no clean receipt
- The scope story differs — Calendar needs no new scope, Meet does. Bundling them would
  make `cal create` gated on a scope most of its uses don't need.

**Why rejected**: ADR-003. The Meet settings become their own primitive in ADR-036, and the
agent writes the two-step. `conferenceId` on read (decision 1) is what makes that cheap.

## Consequences

### Positive

- An invite created from Desk can be a working remote meeting
- `sendUpdates` is controllable, so an event can be staged quietly and — more importantly —
  an event can be deleted without mailing every attendee
- Guest lists can be hidden, which is the case that actually blocked the reporter
- Meet links appear on every event read, useful independent of the write side
- `conferenceId` gives ADR-036 a handle without a second lookup

### Negative

- `create` and `update` grow a lot of flags. Mitigated by grouping them in `--help` and
  leaving all of them optional with Google's defaults intact.
- `--meet` costs `conferenceDataVersion=1` on every insert, changing the request shape even
  when no conference is requested. Harmless, but it's a shared code path now.
- Conference creation is asynchronous — Google may return `status: pending`, so the link is
  occasionally absent from the immediate response. The receipt reports the status rather
  than pretending the link exists.

### Neutral

- Four flags on `respond`/`delete` that most callers won't pass.

## Implementation Notes

- `src/desk/services/calendar.py` — `create()`, `update()`, `delete()`, `respond()`,
  `_parse_event()`
- `src/desk/commands/cal.py` — `create`, `update`, `delete`, `respond`
- `SEND_UPDATES` value map lives in the service, so the CLI-to-API spelling translation
  happens once

## References

- Issue #80
- [Calendar events.insert](https://developers.google.com/workspace/calendar/api/v3/reference/events/insert)
- ADR-002 (no invented vocabulary), ADR-003 (no cross-service commands)
- ADR-036 (Meet support — the other half of #80/#81)

---
id: 080
title: Calendar Event Fields — Meet Link, Guest Permissions, Notification Control
status: implemented
effort: M
value: An invite created from the CLI can be a real remote meeting with a hidden guest list
created: 2026-07-31
updated: 2026-07-31
adr: docs/decisions/035-calendar-event-fields.md
---

# Idea 080: Calendar Event Fields

## Problem

Issue #80. `desk cal create` / `update` couldn't attach a Meet link, hide the guest list,
control who gets notified, or set location/visibility/free-busy — so any real invite meant
finishing the job in the Calendar web UI.

The `sendUpdates` gap was the sharpest: it was hardcoded to `"all"` in four places, so you
could never *stop* notifications. Deleting an event always mailed a cancellation to every
attendee.

Also found while verifying: `_parse_event()` dropped `hangoutLink`/`conferenceData`, so Desk
couldn't display a Meet link on events that already had one.

## Sketch

Shipped as ADR-035: `--meet`, `--hide-guest-list`, `--no-guest-invites`,
`--guests-can-modify`, `--location`, `--visibility`, `--free`, and
`--send-updates all|external-only|none` (default `all`, preserving prior behavior).
`meetLink` / `conferenceId` / `conferenceStatus` added to every event read.

## Open Questions

- [x] Should `--send-updates` default to `none` instead? **Resolved 2026-08-12: no, leave it
      at `all`.** The premise weakened on inspection — the Calendar UI's own default action
      (adding a guest, hitting the primary button) only notifies that guest, not everyone;
      that scoping is Google doing dedup server-side under `sendUpdates=all`, not a distinct
      API value. `all` already tracks the UI's default lean for adds, and is correctly
      unscoped for deletes/reschedules where every attendee really is affected. See ADR-035
      alternative 2.
- [ ] Boolean flags are one-way: `--hide-guest-list` hides, but there's no `--show-guest-list`
      to undo it. Add the negative forms if anyone needs them.
- [ ] `--meet` on a recurring event attaches one conference to the series; no per-occurrence
      control exists in the API. Untested against a real recurring event.

## Value Signal

Direct user report from real work (scripting a pair of recurring training invites). Everything
except the Meet link and the hidden guest list was already scriptable, so this closed a
concrete blocker rather than a hypothetical one.

## Effort Guess

M — many flags, but each maps 1:1 to an API field. The conference `requestId` idempotency and
the async-creation status were the only subtle parts.

## Notes

- `requestId` is derived from the event (hash of summary + start) rather than random, because
  Calendar treats it as an idempotency key — a retried create must not produce a second
  conference.
- Conference creation is asynchronous, so the receipt reports `conferenceStatus: pending`
  rather than implying a link exists.
- The Meet *settings* half of this work (recording, transcription) is idea 081 / ADR-036,
  deliberately kept out of `cal` per ADR-003.

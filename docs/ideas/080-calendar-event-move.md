---
id: "080"
title: Move an Event Between Calendars
status: idea
effort: S
value: Completes the write surface — currently an event can be created on the wrong calendar but not relocated
created: 2026-09-03
updated: 2026-09-03
adr: null
---

# Idea 080: Move an Event Between Calendars

## Problem

[ADR-034](../decisions/034-calendar-write-target.md) lets a write choose
*which* calendar it targets, but nothing relocates an existing event. An
event created on the wrong calendar has to be deleted and recreated,
which loses the event id, drops attendee RSVP state, and sends a
cancellation plus a fresh invitation to everyone on it.

## Sketch

`desk cal move <event-id> --from <calendar> --to <calendar>`, wrapping
Google's `events.move`. `--from` defaults to `primary`, matching the
`-c` default everywhere else.

`events.move` is a real Calendar operation, so this stays inside Google's
vocabulary (ADR-002) rather than inventing a desk-level copy-and-delete.

## Open Questions

- [ ] Is `move` the right verb, or should this be `cal update
      --calendar-to`? A separate verb is clearer, but it is one more
      command in the tree.
- [ ] Does it need a confirmation prompt? `events.move` notifies
      attendees, which puts it in the same class as `delete`.
- [ ] Behavior when the destination already holds a copy of the event.
- [ ] Recurring events: does the whole series move, or can a single
      instance?

## Value Signal

Noted while writing ADR-034, which explicitly scoped it out. Low urgency
— nobody has asked — but the gap is now visible: `-c` implies a choice of
calendar, and users who can choose one will eventually choose wrong.

## Effort Guess

S. One API call, one command, the usual receipt and dry-run wiring. The
recurring-event question is the only real unknown.

## Notes

- [ADR-034](../decisions/034-calendar-write-target.md) — scoped this out
- [Google Calendar `events.move`](https://developers.google.com/calendar/api/v3/reference/events/move)

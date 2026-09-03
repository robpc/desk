---
id: "079"
title: Which Timezone a Naive Datetime Means
status: idea
effort: M
value: Removes the last piece of implicit zone context from calendar writes
created: 2026-09-03
updated: 2026-09-03
adr: null
---

# Idea 079: Which Timezone a Naive Datetime Means

## Problem

Fixing [issue #89](https://github.com/robpc/desk/issues/89) settled *when*
a naive `--start` / `--end` is localized (per its own date, so DST is
handled), but not *where*. Today a bare `2026-11-11T17:30:00` means
5:30pm in the **machine's** timezone — whatever `TZ` the shell happens to
have.

The issue text described the desired behavior as "the calendar's
timezone," which is a different thing. The two diverge in real cases:

- An agent running in a container set to UTC creates an event for a user
  whose calendar is `America/New_York`. The user asked for 5:30pm and
  gets 12:30pm.
- A user travelling with their laptop on local time writes to a calendar
  that is still on home time.
- A shared team calendar with an explicit timezone, written to from
  laptops in three countries.

The machine's zone is a reasonable default for a CLI a person is typing
into. It is a much weaker default for an agent, which may have no
meaningful local zone at all.

## Sketch

Two independent pieces, either useful alone:

1. **`--timezone` / `-z` on `cal create` and `cal update`.** An explicit
   IANA name (`America/New_York`) applied to naive values. Beats making
   every caller compute an offset, which is the workaround #89 already
   noted is a poor default.

2. **Default to the target calendar's timezone rather than the
   machine's.** `calendars.get` returns a `timeZone` for every calendar,
   and after [ADR-034](../decisions/034-calendar-write-target.md) the
   write commands already resolve which calendar they are writing to, so
   the hook exists. Costs one extra API call per write unless cached.

Google's `events.insert` accepts `start.timeZone` alongside
`start.dateTime`, so this maps onto existing vocabulary (ADR-002) rather
than inventing any.

## Open Questions

- [ ] Is changing the default a breaking change worth making, or should
      the calendar's zone only apply behind an opt-in flag? Anyone whose
      machine and calendar already agree sees no difference, which is
      probably most interactive users — but "probably most" is not
      "all."
- [ ] Precedence when both `-z` and a calendar zone exist. Presumably
      explicit flag wins, then calendar, then machine.
- [ ] Does an explicit offset in the input (`...T17:30:00-08:00`) stay
      authoritative over `-z`? It should, but that needs stating.
- [ ] Should `cal today` / `cal week` boundaries follow the same rule?
      They currently anchor to machine midnight, which has the same
      class of problem for a UTC-hosted agent.
- [ ] Worth caching `calendars.get` alongside the existing
      `calendarList.list` resolution cache.

## Value Signal

Surfaced while fixing #89 — the issue asked for calendar-zone semantics
and got date-correct machine-zone semantics, because the former is a
behavior change and the latter is a bug fix. Splitting them kept the fix
small; this is the remaining half, written down so it isn't lost.

The agent case is the sharp one: an agent has no natural local timezone,
so "the machine's zone" is close to arbitrary for it.

## Effort Guess

M. The parsing change is small. The cost is in deciding the default,
the precedence rules, and whether the read commands move too — plus a
cache so writes don't grow an API call.

## Notes

- Related: [idea 052](052-freebusy-overlap-and-attendee-timezones.md) —
  attendee timezones for scheduling. Different problem (whose clock to
  *display*), adjacent domain.
- [ADR-034](../decisions/034-calendar-write-target.md) added the
  calendar resolution this would hang off.
- [Google Calendar `events.insert`](https://developers.google.com/calendar/api/v3/reference/events/insert)

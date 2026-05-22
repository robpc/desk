---
id: "052"
title: Free/Busy Overlap and Attendee Timezones
status: idea
effort: S
value: Make it trivial for agents to find a time that works for everyone, in everyone's local clock
created: 2026-05-21
updated: 2026-05-21
adr: null
---

# Idea 052: Free/Busy Overlap and Attendee Timezones

## Problem

Agents helping schedule meetings hit two friction points:

1. **Overlap computation is manual.** `desk cal freebusy alice@ bob@ --start … --end …` returns each person's busy blocks. To suggest a meeting time, the agent has to invert each list to free blocks, intersect them, filter by desired duration, and rank — entirely client-side. Doable, but every agent ends up writing the same intersection logic, and small bugs (timezone math, half-open intervals, all-day events) recur.

2. **No signal on attendee timezones.** When asked "find a slot tomorrow that overlaps for me and Bob," an agent has no way to know Bob is on West Coast time. So it might propose 8am Eastern — technically a slot both are free, but 5am for Bob. The Free/Busy API response carries no timezone information per attendee.

These two gaps are independent but compose naturally: if an agent knows both *when* people are free and *what local clock they're on*, it can propose a time that's actually reasonable for everyone.

## Sketch

Stay within ADR-002 (no invented vocabulary) and ADR-003 (toolkit, not workflow). Both gaps map to capabilities Google's APIs already expose — we're just surfacing them.

### Overlap on existing `freebusy`

Add flags to `desk cal freebusy`, not a new verb:

```bash
desk cal freebusy alice@ bob@ \
  --start 2026-05-22T08:00 \
  --end   2026-05-22T18:00 \
  --duration 30m            # only return free windows >= 30min
  --overlap                 # intersect across all queried emails + self
```

With `--overlap`, the response is the set of free windows where **all** queried emails are free (plus the authenticated user's primary, since that's almost always the implicit constraint). Each window includes start, end, and duration. `--json` returns a list of `{start, end, duration_minutes}` ready for the agent to consume.

This is *not* a new "find a meeting" command. It's the same `freebusy` query, post-processed. The verb is Google's; the flag just transforms the response.

### Attendee timezone via `calendars.get`

Add a flag (or fold into `--json` output) on `freebusy` that includes each attendee's calendar timezone when accessible:

```bash
desk cal freebusy alice@ bob@ --start … --end … --json
```

```json
{
  "windows": [...],
  "calendars": {
    "alice@example.com": { "timeZone": "America/Los_Angeles", "source": "shared" },
    "bob@example.com":   { "timeZone": null, "source": "unknown" }
  }
}
```

Behind the scenes: try `calendars.get(calendarId=email)`. If it succeeds (because they've shared their calendar with us, common inside an org), we get `timeZone`. If not, we return `null` with `source: "unknown"` so the agent knows it's guessing. **No invented data — only what Google will give us.**

Also: `desk cal list --json` currently drops the `timeZone` field even for calendars we own. Trivial fix — include it.

### What we do NOT build

Per ADR-003, no "find a meeting time" / "schedule with these people" workflow command. The agent composes: query freebusy with `--overlap --duration 30m`, read timezones, pick a window inside everyone's reasonable working hours, then call `desk cal create` to send the invite. Three primitives, agent-written workflow.

## Open Questions

- [ ] How does `--overlap` handle attendees whose calendars are entirely unreadable (e.g. external emails the API returns no busy data for)? Treat as "always free" (optimistic) or omit them from overlap (conservative)? Lean conservative: error or warn, since silently optimistic would suggest times the external person may not actually be free.
- [ ] Working-hours filtering: should `freebusy --overlap` accept `--working-hours 09:00-17:00` to exclude windows outside business hours, or is that the agent's job? Lean agent's job (ADR-003) — but worth thinking about whether a flag is the same kind of "surfacing existing data" as overlap or whether it's encoding opinion.
- [ ] Timezone fetch is N extra API calls (one per attendee). For 2–5 attendees that's fine; if someone queries 20, it's wasteful. Lazy-fetch only when `--json` includes `calendars` block, or batch via the `freebusy` request's existing structure?
- [ ] How to surface "I tried to fetch their timezone and got 404/403"? `source: "unknown"` covers it but agents may want to distinguish "private" from "doesn't exist."

## Value Signal

Scheduling is one of the most common things agents are asked to help with. The current `freebusy` is a primitive that requires every agent to redo the same math and silently miss timezone context. Both additions are small, both use Google's existing data, both make the toolkit meaningfully more useful without inventing workflow.

Adjacent: idea [[018-calendar-freebusy]] (implemented) raised both questions in its "Open Questions" — this idea is the follow-up.

## Effort Guess

**S**.

- Overlap: ~30 lines of interval-arithmetic client-side. Test coverage is the hard part (boundary cases: zero-length windows, back-to-back busy blocks, single attendee, no overlap exists).
- Timezones: one extra API call per attendee, wrapped in try/except. `calendars.get` already used elsewhere.
- `cal list` timezone fix: 1 line.

## Notes

- The `freebusy.query` API itself accepts a `timeZone` parameter for *response interpretation* (used to interpret the busy block times in that zone), but it does **not** return per-attendee timezones. Confirmed.
- For external attendees whose calendars aren't shared with us, there is no public API that returns their timezone. We should not guess based on email domain or similar heuristics — return `null` and let the agent ask.
- This idea explicitly stays inside ADR-002 (every flag maps to Google's own data/operations) and ADR-003 (no workflow verb; agent composes overlap + tz + create).

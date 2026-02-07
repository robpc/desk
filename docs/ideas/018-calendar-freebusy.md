---
id: "018"
title: Calendar Free/Busy Query
status: idea
effort: S
value: Enable scheduling automation by checking availability
created: 2026-02-07
updated: 2026-02-07
adr: null
---

# Idea 018: Calendar Free/Busy Query

## Problem

Agents scheduling meetings cannot check if attendees are available. The Free/Busy API is a dedicated Google Calendar endpoint for querying availability without exposing event details. This is essential for scheduling automation.

## Sketch

```bash
desk cal freebusy <email>... --start <datetime> --end <datetime>
  <email>                    # One or more email addresses to check
  --start                    # Start of time range (required)
  --end                      # End of time range (required)
  --json                     # JSON output with busy blocks
```

Output (table format):
```
EMAIL                    BUSY PERIODS
alice@example.com        2026-02-07 10:00-11:00, 2026-02-07 14:00-15:30
bob@example.com          2026-02-07 09:00-10:00
charlie@example.com      (no busy periods)
```

JSON output includes the raw busy/free blocks for programmatic use.

## Open Questions

- [ ] What's the maximum time range allowed by the API?
- [ ] How does it handle calendars with restricted visibility?
- [ ] Should we support checking multiple calendars for a single user?
- [ ] How to handle timezone differences between querier and target?

## Value Signal

Free/Busy is a core scheduling primitive. Use cases:
- Finding meeting slots that work for all attendees
- Checking your own availability before committing
- Building scheduling automation (find next available 30-min slot)

This is explicitly a Google API (Freebusy resource), not invented vocabulary.

## Effort Guess

**S** - The Freebusy API is a dedicated endpoint with a simple request/response model. Straightforward to implement once datetime parsing is handled (reuse from existing cal commands).

## Notes

- Google Calendar Freebusy API: `calendar.freebusy.query`
- Only returns busy blocks, not event details (privacy-preserving)
- Works across organizational boundaries if calendar sharing allows
- Natural complement to `desk cal create` for scheduling workflows

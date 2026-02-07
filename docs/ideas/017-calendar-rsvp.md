---
id: "017"
title: Calendar RSVP and Invitation Response
status: idea
effort: M
value: Enable agents to manage meeting invitations
created: 2026-02-07
updated: 2026-02-07
adr: null
---

# Idea 017: Calendar RSVP and Invitation Response

## Problem

Agents managing calendars cannot respond to meeting invitations. When someone invites you to a meeting, you need to accept, decline, or mark as tentative. Currently, Desk can view and create events but cannot respond to invitations from others.

## Sketch

```bash
desk cal invitations                  # List pending invitations
  --max <n>                           # Limit results
  --json                              # JSON output

desk cal respond <event-id> --status <response>
  --status accepted|declined|tentative  # Required: your response
  --message "Optional message"          # Note to organizer
  --json                                # JSON output
```

The `invitations` command filters events where:
- User is an attendee (not organizer)
- User's response status is "needsAction"

The `respond` command updates the user's attendee entry on the event.

## Open Questions

- [ ] How does the Calendar API handle RSVP? Is it a PATCH on the attendee object?
- [ ] Does responding send an email to the organizer automatically?
- [ ] Can you respond to recurring events (single instance vs all)?
- [ ] What happens if you respond to an event you organize?

## Value Signal

Meeting management is incomplete without RSVP capability. This is a fundamental calendar operation. Use cases:
- Agents that auto-accept meetings with certain people
- Agents that decline conflicts automatically
- Bulk decline of old pending invitations

## Effort Guess

**M** - Need to understand how attendee responses work in the Calendar API. The response mechanism might be different from regular event updates. May need to handle recurring events specially.

## Notes

- Google Calendar uses `responseStatus` field: needsAction, declined, tentative, accepted
- The self attendee entry needs to be updated
- Consider: `desk cal respond --all-pending --status declined` for bulk operations?
- This is Google's vocabulary - "respond" and "RSVP" are standard calendar terms

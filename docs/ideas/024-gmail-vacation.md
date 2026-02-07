---
id: "024"
title: Gmail Vacation Responder
status: idea
effort: S
value: Enable automated out-of-office management
created: 2026-02-07
updated: 2026-02-07
adr: null
---

# Idea 024: Gmail Vacation Responder

## Problem

Gmail's vacation responder (auto-reply) cannot be managed through Desk. Users going on vacation or setting up out-of-office messages must use the Gmail UI. Agents cannot programmatically enable/disable vacation responses.

## Sketch

```bash
desk mail vacation-status              # Show current vacation settings
  --json                               # JSON output

desk mail vacation                     # Set vacation responder
  --enable                             # Turn on (default if setting message)
  --disable                            # Turn off
  --message "I'm out of office..."     # Auto-reply message (HTML supported)
  --subject "Out of Office"            # Reply subject (optional)
  --start 2026-02-10                   # Start date (optional)
  --end 2026-02-17                     # End date (optional)
  --contacts-only                      # Only reply to contacts
  --domain-only                        # Only reply to same domain
```

Output for `vacation-status`:
```
Status: ENABLED
Subject: Out of Office
Message: I'm away until Feb 17. For urgent matters, contact...
Start: 2026-02-10
End: 2026-02-17
Restrictions: contacts only
```

## Open Questions

- [ ] Does the API support HTML in vacation messages?
- [ ] How do start/end dates interact with timezone?
- [ ] What happens when you set message without explicit enable?
- [ ] Can you have multiple vacation responders (e.g., different for internal/external)?

## Value Signal

Vacation responder management enables:
- Automated OOO setup based on calendar (agent sees vacation event, sets responder)
- Quick enable/disable from command line
- Scripted vacation setup before trips

This is a standard Gmail Settings feature.

## Effort Guess

**S** - Gmail Settings API has a `vacationSettings` resource with simple get/update. Straightforward to implement.

## Notes

- Gmail API: `users.settings.getVacation` and `users.settings.updateVacation`
- Part of Gmail Settings, not message operations
- May require `gmail.settings.basic` scope
- Related: idea 015 (filters) also uses Gmail Settings API

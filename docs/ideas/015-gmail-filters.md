---
id: "015"
title: Gmail Filters Management
status: idea
effort: M
value: Enable programmatic inbox rule management for automation
created: 2026-02-07
updated: 2026-02-07
adr: null
---

# Idea 015: Gmail Filters Management

## Problem

Users and agents cannot manage Gmail filters (inbox rules) through Desk. Filters are a core Gmail feature that automate message handling - applying labels, archiving, forwarding, etc. Without filter management, agents must repeatedly process messages that could be handled automatically.

## Sketch

```bash
desk mail filters                    # List all filters
desk mail filter <filter-id>         # Show filter details (criteria + actions)
desk mail create-filter              # Create a new filter
  --from <address>
  --to <address>
  --subject <text>
  --has-attachment
  --query <gmail-query>              # Raw Gmail search syntax
  --add-label <label>                # Action: add label
  --remove-label <label>             # Action: remove label
  --archive                          # Action: skip inbox
  --mark-read                        # Action: mark as read
  --star                             # Action: star
  --forward <email>                  # Action: forward
  --never-spam                       # Action: never mark as spam
desk mail delete-filter <filter-id>  # Delete a filter
```

Output format matches existing patterns - table by default, `--json` for structured output.

## Open Questions

- [ ] Does Gmail API support all filter actions available in the UI?
- [ ] How to handle filter ordering/priority?
- [ ] Should we support updating existing filters or just delete + recreate?
- [ ] How to represent complex criteria (AND vs OR)?

## Value Signal

Filters are fundamental to inbox management. Power users and automation systems rely heavily on them. Being able to programmatically manage filters enables:
- Automated inbox triage setup
- Backup/restore of filter configurations
- Auditing of existing rules

## Effort Guess

**M** - Gmail Settings API is separate from main Gmail API. Need to understand the filter object model and how criteria/actions map. Core implementation is straightforward once API is understood.

## Notes

- Gmail filters use the `gmail.settings.basic` or `gmail.settings.sharing` scope
- Filters are part of the Settings resource, not Messages
- Related: idea 000 anti-patterns - this is a single-service primitive, not a workflow

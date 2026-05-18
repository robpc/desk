---
id: "015"
title: Gmail Filters Management
status: implemented
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

- [x] **Does Gmail API support all filter actions available in the UI?** — No. See "API Constraints Discovered" below.
- [ ] How to handle filter ordering/priority?
- [ ] Should we support updating existing filters or just delete + recreate? (Note: there's no PATCH/PUT verb — only POST and DELETE. Delete-before-create is dangerous; see implementation note below.)
- [ ] How to represent complex criteria (AND vs OR)?

## API Constraints Discovered

Hit empirically during a bulk inbox cleanup using the Gmail Settings API directly (2026-05-18). These directly affect what a `desk mail create-filter` command can support and the error messages it should produce.

**`action.addLabelIds`:**
- ✅ User labels and most system labels (INBOX, IMPORTANT, STARRED, etc.)
- ❌ `SPAM` — `HTTP 400 "Invalid label SPAM in AddLabelIds"`
- ❌ `TRASH` — same pattern
- Consequence: there is no API equivalent of the UI's "Mark as spam" / "Delete" actions. A `--mark-as-spam` flag on `desk mail create-filter` is unimplementable; the closest is a normal filter routing mail to a user label, plus a one-time `batchModify` of historical mail to add `SPAM`.

**`action.removeLabelIds`:**
- ✅ `INBOX`, `UNREAD`, `IMPORTANT` (the only ones effectively used by the UI's "Skip Inbox", "Mark as read", "Never mark as important" actions)
- ❌ `CATEGORY_PROMOTIONS`, `CATEGORY_UPDATES`, `CATEGORY_PERSONAL`, `CATEGORY_SOCIAL`, `CATEGORY_FORUMS` — `HTTP 400 "Invalid label(s) ... in RemoveLabelIds"`
- ❌ Any user-created label (e.g., `Label_5809875640041094720`) — same error
- Consequence: a `--remove-label` flag must validate input upfront against a known whitelist (or just relay Gmail's error verbatim). Removing categories or user labels at filter-trigger time is impossible via API.

**Workaround for the disallowed operations:** `users.messages.batchModify` has no such restriction. It can add/remove any label including SPAM, TRASH, categories, and user labels. The pattern for desk would be:
- Filter for real-time routing on incoming mail: limited to the allowed action set above
- batchModify for periodic / one-shot cleanup: can express anything

**Implementation footgun:** Gmail filters have no PATCH verb. To "modify" a filter you must DELETE and POST a new one. If validation of the new filter happens server-side and fails, the old filter is gone. **Validate the new filter's action shape against the API constraints above BEFORE any delete loop**, e.g. by creating a single test filter end-to-end first. Otherwise a bulk update can wipe filters mid-loop with no easy recovery.

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

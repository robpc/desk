---
id: 007
title: Drafts Management
status: implemented
effort: M
value: Compose now, review/send later - useful for agent workflows
created: 2025-02-06
updated: 2026-02-07
adr: null
---

# Idea 007: Drafts Management

## Problem

Sometimes you want to compose an email but review it before sending. Agents might draft responses for human review. Currently no way to work with drafts from CLI.

## Sketch

```bash
# Create a draft
desk mail draft create --to "user@example.com" --subject "Proposal" --body "..."

# List drafts
desk mail drafts
desk mail drafts --json

# Read a draft
desk mail draft read <draft-id>

# Send a draft
desk mail draft send <draft-id>

# Delete a draft
desk mail draft delete <draft-id>

# Update a draft
desk mail draft update <draft-id> --body "Updated content"
```

## Use Cases

1. **Agent workflow**: Agent drafts response, human reviews in Gmail web UI, then sends
2. **Batch preparation**: Prepare multiple emails, review all, then send
3. **Templates**: Create draft templates, duplicate and customize

## Open Questions

- [ ] Command structure: `desk mail draft <action>` vs `desk mail drafts` (list)?
- [ ] How does draft-send interact with send command?
- [ ] Should draft create return the draft ID for scripting?

## Value Signal

Useful for agent-assisted email where human stays in the loop for sending.

## Effort Guess

M - Multiple CRUD operations, but Gmail Drafts API is straightforward.

## Notes

- Gmail API: `users.drafts.*` endpoints
- Drafts are tied to messages - a draft contains a message object

## Implementation (2026-02-07)

Implemented full CRUD for drafts:

```bash
# List drafts
desk mail drafts
desk mail drafts --json

# Create a draft
desk mail draft create --to "user@example.com" --subject "Proposal" --body "..."

# Read a draft
desk mail draft read DRAFT_ID

# Send a draft
desk mail draft send DRAFT_ID

# Delete a draft
desk mail draft delete DRAFT_ID

# Update a draft (preserves unchanged fields)
desk mail draft update DRAFT_ID --subject "New subject"
desk mail draft update DRAFT_ID --body "Updated content"
```

**Decisions made:**
- Command structure: `desk mail drafts` for list, `desk mail draft <action>` for operations
- Draft create returns draft ID in output (and in JSON for scripting)
- Update preserves fields not specified (fetches existing, merges changes)

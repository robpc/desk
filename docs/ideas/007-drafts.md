---
id: 007
title: Drafts Management
status: idea
effort: M
value: Compose now, review/send later - useful for agent workflows
created: 2025-02-06
updated: 2025-02-06
adr: null
---

# Idea 007: Drafts Management

## Problem

Sometimes you want to compose an email but review it before sending. Agents might draft responses for human review. Currently no way to work with drafts from CLI.

## Sketch

```bash
# Create a draft
gmail draft create --to "user@example.com" --subject "Proposal" --body "..."

# List drafts
gmail drafts
gmail drafts --json

# Read a draft
gmail draft read <draft-id>

# Send a draft
gmail draft send <draft-id>

# Delete a draft
gmail draft delete <draft-id>

# Update a draft
gmail draft update <draft-id> --body "Updated content"
```

## Use Cases

1. **Agent workflow**: Agent drafts response, human reviews in Gmail web UI, then sends
2. **Batch preparation**: Prepare multiple emails, review all, then send
3. **Templates**: Create draft templates, duplicate and customize

## Open Questions

- [ ] Command structure: `gmail draft <action>` vs `gmail drafts` (list) + `gmail draft-create`, etc.?
- [ ] How does draft-send interact with send command?
- [ ] Should draft create return the draft ID for scripting?

## Value Signal

Useful for agent-assisted email where human stays in the loop for sending.

## Effort Guess

M - Multiple CRUD operations, but Gmail Drafts API is straightforward.

## Notes

- Gmail API: `users.drafts.*` endpoints
- Drafts are tied to messages - a draft contains a message object

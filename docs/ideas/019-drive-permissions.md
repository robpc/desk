---
id: "019"
title: Drive Permissions Management
status: implemented
effort: M
value: Complete the sharing story with view/revoke capabilities
created: 2026-02-07
updated: 2026-02-07
adr: null
---

# Idea 019: Drive Permissions Management

## Problem

Desk has `desk drive share` to grant access but no way to:
- View who has access to a file
- Revoke access from specific users
- Transfer ownership

This asymmetry makes sharing management incomplete. You can share but can't audit or unshare.

## Sketch

```bash
desk drive permissions <file-id>      # List all permissions on a file
  --json                              # JSON output with full permission details

desk drive unshare <file-id> <email>  # Remove a user's access
  --dry-run                           # Preview without making changes

desk drive transfer-owner <file-id> <email>  # Transfer ownership
  --dry-run                           # Preview
```

Output for `permissions`:
```
ROLE      TYPE      EMAIL/DOMAIN           NAME
owner     user      alice@example.com      Alice Smith
writer    user      bob@example.com        Bob Jones
reader    anyone    (anyone with link)     -
commenter domain    example.com            Example Corp
```

## Open Questions

- [ ] How to handle "anyone with link" permissions in unshare?
- [ ] Does transferring ownership require the recipient to accept?
- [ ] Should we support permission updates (change reader to writer)?
- [ ] How to handle inherited permissions from parent folders?

## Value Signal

Sharing audit is a common need:
- Security reviews: "who has access to this sensitive doc?"
- Cleanup: "remove access for departed team members"
- Handoffs: "transfer ownership when someone leaves"

Without these commands, users must use the Drive UI for permission management.

## Effort Guess

**M** - Drive Permissions API is well-documented but has edge cases (link sharing, domain sharing, inherited permissions). Need to handle different permission types gracefully.

## Notes

- Drive uses `permissions` resource with CRUD operations
- Permission types: user, group, domain, anyone
- Roles: owner, organizer, fileOrganizer, writer, commenter, reader
- Ownership transfer has special requirements (same domain, etc.)
- Related: `desk drive share` already exists, this completes the story

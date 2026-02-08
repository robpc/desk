---
id: 031
title: Enhanced Dry-Run with Target Details
status: planned
effort: S
value: Agents can preview exactly what will happen before committing
created: 2025-02-07
updated: 2025-02-07
adr: 004-agent-first-cli.md
---

# Idea 031: Enhanced Dry-Run with Target Details

## Problem

Dry-run is already implemented (Idea 011), but the output is minimal:

```
Would archive 3 message(s)
```

For agent safety, we need to show *what* would be affected so agents can verify they're targeting the right items.

## Sketch

Enhanced dry-run shows target details:

```bash
$ desk mail trash abc123 --dry-run --json
```

```json
{
  "dry_run": true,
  "would_execute": "trash",
  "targets": [
    {
      "id": "abc123",
      "subject": "Q4 Report",
      "from": "boss@company.com",
      "date": "2025-02-05"
    }
  ],
  "reversible": true,
  "undo_would_be": "desk mail untrash abc123",
  "warnings": []
}
```

### With Warnings

If the operation is destructive or irreversible:

```bash
$ desk mail send --to "all@company.com" --subject "Update" --body "..." --dry-run --json
```

```json
{
  "dry_run": true,
  "would_execute": "send",
  "targets": [
    {
      "to": ["all@company.com"],
      "subject": "Update",
      "body_preview": "First 100 characters...",
      "body_length": 523
    }
  ],
  "reversible": false,
  "undo_would_be": null,
  "warnings": [
    "This action cannot be undone",
    "Recipient 'all@company.com' may be a mailing list"
  ]
}
```

### Human-Readable Mode

```
DRY RUN — No changes made

Would trash 1 message:
  • Q4 Report (from boss@company.com, 2025-02-05)

This action is reversible.
Undo would be: desk mail untrash abc123
```

## Open Questions

- [ ] How much detail per target? (Subject + from + date seems right)
- [ ] For large batches (100+ items), show first N with "and X more"?
- [ ] Should warnings be a standard set or free-form?

## Value Signal

Catches agent mistakes before they happen. "You're about to trash an email from your boss titled 'Q4 Report' — is that right?" is much safer than "Would trash 1 message."

## Effort Guess

S - Dry-run infrastructure exists. Need to fetch target details and enhance output format. Most work is adding the target detail fetching.

## Notes

Depends on: Idea 028 (Agent-First Framework)

Builds on existing: Idea 011 (Dry-Run Mode)

Related: ADR-004, Idea 030 (receipts share similar target detail structure)

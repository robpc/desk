---
id: "020"
title: Drive Copy
status: implemented
effort: S
value: Enable template workflows and file duplication
created: 2026-02-07
updated: 2026-02-07
adr: null
---

# Idea 020: Drive Copy

## Problem

There's no way to copy a file in Drive through Desk. Copy is a native Drive operation distinct from download+upload - it preserves Google Docs/Sheets format, permissions options, and is faster for large files. Essential for template-based workflows.

## Sketch

```bash
desk drive copy <file-id> [--name "Copy Name"] [--folder <folder-id>]
  <file-id>           # Source file to copy
  --name              # Name for the copy (default: "Copy of <original>")
  --folder            # Destination folder (default: same as original)
  --json              # Output new file details as JSON
```

Output:
```
Copied to: Copy of Q4 Report
File ID: 1abc...xyz
Location: /Reports/2026/
```

## Open Questions

- [ ] Should copying preserve comments? (API option)
- [ ] Should we support copying folders (recursive)?
- [ ] How to handle Google Workspace files vs regular files?
- [ ] Permission handling: copy permissions or start fresh?

## Value Signal

Copy is fundamental for:
- Template workflows: copy template doc, fill in details
- Backup before major edits
- Creating variations of existing files
- Sharing a snapshot without link sharing

Google Drive UI has "Make a copy" as a primary action.

## Effort Guess

**S** - Drive API has a simple `files.copy` method. Main work is parameter mapping and output formatting. Should follow existing patterns from upload/download.

## Notes

- Drive API: `files.copy` method
- Can specify new parent, new name, and whether to copy comments
- Works on all file types including Google Workspace files
- Faster than download+upload, especially for large files
- Natural complement to existing file operations

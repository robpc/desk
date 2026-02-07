---
id: "021"
title: Sheets Tab/Sheet Management
status: idea
effort: M
value: Complete spreadsheet operations with sheet-level control
created: 2026-02-07
updated: 2026-02-07
adr: null
---

# Idea 021: Sheets Tab/Sheet Management

## Problem

Google Spreadsheets contain multiple sheets (tabs). Desk can read/write data to sheets but cannot manage the sheets themselves - no way to list sheets, add new ones, rename them, or delete them. This makes spreadsheet structure management impossible.

## Sketch

```bash
desk sheets list-sheets <spreadsheet-id>    # List all sheets/tabs
  --json                                    # JSON with sheet IDs and properties

desk sheets add-sheet <spreadsheet-id>      # Add a new sheet
  --name "Sheet Name"                       # Name for new sheet (required)
  --index <n>                               # Position (0-based, optional)
  --json                                    # Output new sheet details

desk sheets delete-sheet <spreadsheet-id> --sheet-id <id>
  --sheet-id                                # Sheet ID to delete (required)
  --dry-run                                 # Preview without deleting
  --yes                                     # Skip confirmation

desk sheets rename-sheet <spreadsheet-id> --sheet-id <id> --name "New Name"
  --sheet-id                                # Sheet ID to rename (required)
  --name                                    # New name (required)
```

Output for `list-sheets`:
```
SHEET ID    NAME              INDEX    ROWS    COLS
0           Summary           0        100     26
1234567     Q1 Data           1        500     15
2345678     Q2 Data           2        450     15
```

## Open Questions

- [ ] How to reference sheets by name vs ID in other commands?
- [ ] Should delete require confirmation or just `--yes` to skip?
- [ ] Support for copying sheets within or between spreadsheets?
- [ ] Support for hiding/unhiding sheets?

## Value Signal

Sheet management is needed for:
- Creating structured spreadsheets programmatically
- Adding monthly/quarterly sheets to existing files
- Cleaning up unused sheets
- Reorganizing spreadsheet structure

Currently users must use Sheets UI for any structural changes.

## Effort Guess

**M** - Sheets API uses `batchUpdate` with specific request types for sheet operations. Need to understand the request format for add/delete/rename. More complex than simple read/write.

## Notes

- Sheets API: `spreadsheets.batchUpdate` with requests like `addSheet`, `deleteSheet`, `updateSheetProperties`
- Sheet ID is different from spreadsheet ID
- Sheet index controls tab order
- Consider: `desk sheets read` already accepts `--sheet-id`, these commands complete the picture
- "Sheet" is Google's terminology (tabs within a spreadsheet)

---
id: 046
title: Drive Folder Read + Office File Support
status: implemented
effort: M
value: Batch-read folders and render Office files as text for agents
created: 2026-03-03
updated: 2026-05-18
adr: docs/decisions/014-drive-folder-read-and-office-support.md
---

# Idea 046: Drive Folder Read + Office File Support

## Problem

Reading all files in a Google Drive folder requires N separate `desk drive read <id>` calls. Worse, uploaded Office files (.docx, .xlsx) come back as binary garbage because `read()` downloads them raw.

## Sketch

1. Add `desk drive list-folder <folder-id>` to enumerate files in a folder (metadata only)
2. Extend `desk drive read` with `--stdin` and multi-ID support for batch reading
3. Compose: `desk drive list-folder <id> --json | jq -r '.files[].id' | desk drive read --stdin`
4. Add local conversion for .docx (python-docx) and .xlsx (openpyxl) in `DriveClient.read()`

## Value Signal

Hit this in a real workflow: reading 20+ files from a clustering research folder. The CSVs and Google-native files worked, but the .docx and .xlsx were unreadable.

## Effort Guess

M — Two distinct features but both are straightforward. Main complexity is Office file edge cases (encrypted files, multi-sheet xlsx, tables in docx).

## Notes

See ADR-014 for full decision record.

---
id: "038"
title: Docs Find-and-Replace
status: implemented
effort: S
value: Enable templating workflows — copy a template doc and substitute placeholders without replacing the entire document
created: 2026-02-12
updated: 2026-02-12
adr: null
---

# Idea 038: Docs Find-and-Replace

## Problem

`desk docs update` only supports append, prepend, and full replace modes. There's no way to substitute specific text in a document while preserving the rest of the content and formatting.

This came up in a real workflow: copying an interview template doc via `desk drive copy`, then needing to replace the placeholder title "Interview Template" with the actual interview name. The current workaround is to read the doc, do a string replace in the shell, then `desk docs update --mode replace` — but this round-trips through plain text and loses all Google Docs formatting (bold, headings, etc.).

## Sketch

Add a `--find` flag to `desk docs update` that uses the Google Docs API's `replaceAllText` batch request:

```bash
# Replace all occurrences of a string
desk docs update <id> "Interview 2026-02-12 – Maya Murry" --find "Interview Template"

# Case-insensitive
desk docs update <id> "new text" --find "old text" --ignore-case
```

The Google Docs API natively supports `ReplaceAllTextRequest` with `containsText` (text + matchCase), so this maps directly to a single API call — no need to read-then-rewrite.

## Open Questions

- [ ] Should `--find` imply replace-all, or should there be a `--count` limit?
- [ ] Support regex, or just literal strings? (API only supports literal)

## Value Signal

Templating is a common agent workflow — copy a template, fill in placeholders. The current workaround destroys formatting, which matters for shared docs.

## Effort Guess

S — single API call (`documents.batchUpdate` with `ReplaceAllTextRequest`), one new flag on an existing command.

## Notes

- Google Docs API reference: `ReplaceAllTextRequest` in `documents.batchUpdate`
- Current workaround in `~/bin/interview-prep` reads plain text, does sed replace, writes back with `--mode replace` — works but loses formatting

---
id: "023"
title: Drive Comments
status: implemented
effort: S
value: Enable feedback on any Drive file
created: 2026-02-07
updated: 2026-02-07
adr: null
---

# Idea 023: Drive Comments

## Problem

Any file in Google Drive can have comments (not just Docs). PDFs, images, and other files support comments for feedback. This is useful for review workflows on non-Google-native files.

## Sketch

```bash
desk drive comments <file-id>              # List all comments
  --include-resolved                       # Include resolved comments
  --json                                   # JSON output

desk drive add-comment <file-id>           # Add a comment
  --text "Comment text"                    # Comment content (required)
  --json                                   # Output new comment details

desk drive resolve-comment <file-id> <comment-id>
  --reopen                                 # Reopen instead of resolve

desk drive reply-comment <file-id> <comment-id>
  --text "Reply text"                      # Reply content (required)
```

Same API and patterns as Docs comments (idea 022), but:
- No text anchoring (non-text files)
- Works on any file type
- Simpler implementation

## Open Questions

- [ ] Should this share implementation with Docs comments?
- [ ] How does anchoring work for non-text files (images, PDFs)?
- [ ] Should we distinguish between file-level and content-anchored comments?

## Value Signal

Drive comments enable:
- Feedback on uploaded PDFs, images, etc.
- Review workflows for any file type
- Discussion threads attached to files

## Effort Guess

**S** - If implemented after Docs comments (idea 022), this is mostly reuse. Same Drive API, just without the anchoring complexity. Could be implemented as shared infrastructure.

## Notes

- Same Drive API as Docs comments
- Simpler because no content anchoring needed for most file types
- Could share 90% of implementation with idea 022
- Consider implementing 022 and 023 together as shared comment infrastructure

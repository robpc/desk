---
id: "022"
title: Docs Comments
status: idea
effort: M
value: Enable document review and feedback workflows
created: 2026-02-07
updated: 2026-02-07
adr: null
---

# Idea 022: Docs Comments

## Problem

Google Docs supports comments and suggestions for collaborative editing. Desk cannot read or create comments, limiting its usefulness for review workflows. Agents reviewing documents can't add feedback programmatically.

## Sketch

```bash
desk docs comments <document-id>           # List all comments
  --include-resolved                       # Include resolved comments
  --json                                   # JSON output with full comment data

desk docs add-comment <document-id>        # Add a comment
  --text "Comment text"                    # Comment content (required)
  --anchor "quoted text"                   # Text to anchor comment to (optional)
  --json                                   # Output new comment details

desk docs resolve-comment <document-id> <comment-id>
  --reopen                                 # Reopen instead of resolve

desk docs reply-comment <document-id> <comment-id>
  --text "Reply text"                      # Reply content (required)
```

Output for `comments`:
```
ID          AUTHOR              ANCHOR              CONTENT
abc123      alice@example.com   "quarterly goals"   Should we add metrics?
def456      bob@example.com     "next steps"        Needs more detail
```

## Open Questions

- [ ] How does anchoring work in the API? Character offsets or text matching?
- [ ] Can we support suggesting edits (suggestion mode)?
- [ ] How to handle comments on deleted text?
- [ ] Should we support @mentions in comments?

## Value Signal

Comments enable:
- Automated document review (agent adds feedback)
- Tracking review status
- Processing feedback programmatically
- QA workflows on documentation

Google Docs comments are a first-class feature of the collaboration model.

## Effort Guess

**M** - Drive API handles comments (not Docs API). Need to understand comment anchoring, replies, and resolution. The comment threading model adds complexity.

## Notes

- Comments use the Drive API (`comments` resource), not Docs API
- Comments can have replies (threaded)
- Comments can be anchored to specific content
- Resolution is a state change, not deletion
- Related: idea 023 (Drive comments) - same API, different context

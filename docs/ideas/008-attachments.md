---
id: 008
title: Attachment Handling
status: idea
effort: M
value: Download and process email attachments from CLI
created: 2025-02-06
updated: 2026-02-06
adr: null
---

# Idea 008: Attachment Handling

## Problem

Emails often have attachments (PDFs, images, documents). Currently no way to access them from CLI. Agents processing email often need to extract and analyze attachments.

## Sketch

```bash
# List attachments for a message
desk mail attachments <message-id>
desk mail attachments <message-id> --json

# Download all attachments
desk mail download <message-id>                    # to current dir
desk mail download <message-id> --output ./files/  # to specific dir

# Download specific attachment
desk mail download <message-id> --filename "report.pdf"

# Pipe attachment to stdout (for processing)
desk mail attachment <message-id> "report.pdf" | pdftotext - -
```

## Use Cases

1. **Invoice processing**: Download PDF invoices for parsing
2. **Image analysis**: Extract images for vision models
3. **Document archival**: Bulk download attachments from a search
4. **Data extraction**: Process CSV/Excel attachments

## Open Questions

- [ ] Command naming: `attachments` (list) vs `download` vs `attachment` (single)?
- [ ] Handle filename collisions?
- [ ] Support batch download from multiple messages?
- [ ] Size limits / warnings for large attachments?

## Value Signal

High value for agent workflows that process incoming documents.

## Effort Guess

M - Gmail API attachment handling requires fetching message parts, base64 decoding. Not complex but fiddly.

## Notes

- Gmail API: attachments are in `message.payload.parts[].body.attachmentId`
- Need `users.messages.attachments.get` to fetch attachment data
- Attachments are base64 encoded

---
id: 037
title: Surface Linked Docs and URLs in Email Output
status: idea
effort: M
value: Agents can't follow links or access linked Google Docs from emails — key context is invisible
created: 2026-02-10
updated: 2026-02-10
adr: null
---

# Idea 037: Surface Linked Docs and URLs in Email Output

## Problem

When an agent reads an email with `desk mail read`, linked content is invisible:

1. **URLs stripped from plain text** — The plain text body shows link text ("Open meeting notes") but drops the URL. An agent sees the words but can't follow the link.

2. **Gmail rich link cards not surfaced** — Gmail renders linked Google Docs, Drive files, and similar resources as visual "attachment" cards at the bottom of emails (with thumbnails, titles, "Add to Drive" buttons). Users see these as attachments. But they aren't MIME attachments — they're rich link previews Gmail constructs from embedded URLs. `desk mail attachments` returns "No attachments" for these.

Real-world example: Gemini meeting notes emails include a Google Doc with the full transcript. Gmail shows it as an attachment card labeled "Cross-Platform D..." with a Docs icon. An agent using desk sees neither the link nor the "attachment" — it only gets the abbreviated Gemini summary, missing the full transcript.

## Sketch

### Option A: Preserve URLs in plain text output

When rendering the plain text body, inline URLs from the HTML version:

```
Open meeting notes
  https://docs.google.com/document/d/1zLIvrcdb.../edit

Meeting records Document Notes by Gemini
  https://docs.google.com/document/d/1zLIvrcdb.../edit
```

### Option B: Add a `--links` flag

```bash
desk mail read MESSAGE_ID --links
```

Returns a list of URLs found in the email, with context about what they link to.

### Option C: Surface linked Google Docs as virtual attachments

Make `desk mail attachments` return linked Google Docs/Drive files alongside real MIME attachments, distinguished by type:

```json
{
  "attachments": [],
  "linked_documents": [
    {
      "type": "google-doc",
      "title": "Cross-Platform Drop-In - Notes by Gemini",
      "url": "https://docs.google.com/document/d/1zLIvrcdb.../edit",
      "readable_via": "desk docs read 1zLIvrcdb..."
    }
  ]
}
```

This is the most agent-friendly option — it tells the agent exactly what's there and how to access it.

## Open Questions

- [ ] How does Gmail represent these rich link cards in the API? Is there metadata beyond what's in the HTML?
- [ ] Should `desk mail read` always show links, or only with a flag?
- [ ] Should linked Google Docs be auto-readable (i.e., `desk mail read` could inline the doc content with a `--expand-links` flag)?

## Value Signal

Hit this in real usage today — an agent couldn't access meeting notes because the Google Doc link was invisible. Had to manually extract the URL from raw HTML email via the Gmail API, then pipe it to `desk docs read`. An agent-first CLI should handle this seamlessly.

## Effort Guess

M — Need to parse HTML for URLs, identify Google Workspace links specifically, and decide on the right output format. The virtual attachments approach (Option C) requires understanding Gmail's rich link card behavior.

## Notes

- This connects to ADR-004 (Agent-First CLI) — agents can't click links, so the CLI must surface them explicitly.
- Google Workspace links are the highest-value subset (Docs, Sheets, Drive) since desk can already read those via `desk docs read`, `desk sheets read`, etc. The CLI could provide a complete read-through path.

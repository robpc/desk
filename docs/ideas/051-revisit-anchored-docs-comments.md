---
id: "051"
title: Revisit Anchored Docs Comments
status: parked
effort: S
value: Agent review workflows on Docs — pin comments to specific paragraphs
created: 2026-05-21
updated: 2026-05-21
adr: null
---

# Idea 051: Revisit Anchored Docs Comments

## Problem

Agents leaving review-style feedback on a Google Doc ("two notes on this doc, both about specific bullets") cannot pin comments to the relevant paragraph. The recipient sees floating doc-level threads and has to guess which passage each one refers to.

Originally filed as GitHub issue #39 (closed). Reopened here as a parked idea so the investigation isn't lost.

## Why This Is Parked

Investigated 2026-05-21. **The public Google Workspace APIs do not currently expose anchored comment creation for Google Docs.**

- **Drive API (`comments.create`)** accepts an `anchor` JSON string and Google's docs describe a documented shape: `{"r": "head", "a": [{"line": N, "rev": "head"}]}`. Reality: multiple 2025 developer reports show that no matter what anchor JSON is passed, the Docs UI renders the comment as an unanchored floating thread. The anchor string is stored on the resource but ignored on render.
  - Reference: [latenode thread](https://community.latenode.com/t/how-to-programmatically-add-text-anchored-comments-in-google-docs/11440), [issuetracker 357985444](https://issuetracker.google.com/issues/357985444).
- **Docs API (`documents.batchUpdate`)** has 42 request types covering text, styling, tables, images, headers/footers. **None of them create comments.** Verified directly from [the Docs API request reference](https://developers.google.com/workspace/docs/api/reference/rest/v1/documents/request).
- **The web Docs client** uses internal `kix.*` anchor identifiers via private RPCs. That format is not part of the public contract and reverse-engineering it is fragile — the IDs are tied to internal document state that third parties can't construct.

Without true anchoring, a `--quote` flag would only prepend `> "<text>"` to the comment body. That's a cosmetic convention an agent can already produce in its prompt — not worth a CLI feature.

## Trigger to Revisit

Open this back up if **any** of these happen:

- Google ships a public `createComment` request in the Docs API `batchUpdate`.
- Google updates the Drive `comments.create` anchor documentation with a region type that actually renders pinned in the Docs UI (e.g., a `txt` / `range` region with confirmed rendering).
- A third-party library publishes a working `kix.*` anchor generator with reproducible results.

## Sketch (if/when we revisit)

Assuming Google exposes the capability:

- `desk docs comment <doc-id> --quote "<text>" --text "<comment>"` — find the quote via the Docs API content stream, build the anchor (or Docs API request), call the appropriate endpoint.
- `--anchor-range start:end` for direct index targeting (reuses `desk docs inspect` output).
- `--occurrence N` to disambiguate when `--quote` matches multiple places; error if ambiguous and no occurrence given.

Command should live under `desk docs` (matches user mental model) regardless of which API surfaces it.

## Notes

- The existing `desk drive add-comment` already creates unanchored comments on any Drive file including Docs. That's the current ceiling of what's possible.
- Sheets/Slides anchoring uses different region formats and is explicitly out of scope here.
- Closed GitHub issue: #39.
